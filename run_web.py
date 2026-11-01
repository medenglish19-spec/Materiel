"""Single entry point for source and packaged Windows application runs."""

import ctypes
import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_MB_ICONERROR = 0x00000010
_MB_OK = 0x00000000


def _fallback_data_dir() -> Path:
    executable_dir = Path(sys.executable).resolve().parent
    override = os.getenv("MATERIEL_DATA_DIR")
    if override:
        directory = Path(os.path.expandvars(override)).expanduser()
        return directory if directory.is_absolute() else executable_dir / directory

    try:
        configured_dir = (executable_dir / "materiel-data-dir.txt").read_text(
            encoding="utf-8"
        ).strip()
    except OSError:
        configured_dir = ""
    if configured_dir:
        directory = Path(os.path.expandvars(configured_dir)).expanduser()
        return directory if directory.is_absolute() else executable_dir / directory

    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "Materiel" / "data"
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Materiel" / "data"
    return Path.home() / "AppData" / "Local" / "Materiel" / "data"


def _write_fatal_error(error: BaseException) -> Path:
    log_path = _fallback_data_dir() / "logs" / "error.log"
    message = (
        f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} FATAL: {error!r}\n"
        f"{''.join(traceback.format_exception(type(error), error, error.__traceback__))}\n"
    )
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(message)
    except OSError:
        fallback = Path(os.getenv("TEMP") or Path.home()) / "Materiel-error.log"
        try:
            with fallback.open("a", encoding="utf-8") as log_file:
                log_file.write(message)
            return fallback
        except OSError:
            return log_path
    return log_path


def _show_fatal_error(error: BaseException, log_path: Path) -> None:
    message = (
        "تعذر تشغيل تسيير ومحاسبة العتاد.\n\n"
        f"السبب: {error}\n\n"
        "أرسل سجل الأخطاء إلى الدعم الفني:\n"
        f"{log_path}"
    )
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "Materiel", _MB_OK | _MB_ICONERROR)
            return
        except (AttributeError, OSError):
            pass
    if sys.stderr is not None:
        sys.stderr.write(message + "\n")


def _identity() -> str:
    return "Materiel"


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_bool,
        ctypes.c_bool,
        ctypes.c_wchar_p,
    ]
    kernel32.CreateEventW.restype = ctypes.c_void_p
    kernel32.OpenEventW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.OpenEventW.restype = ctypes.c_void_p
    kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    kernel32.SetEvent.restype = ctypes.c_bool
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel32.ReleaseMutex.restype = ctypes.c_bool
    return kernel32


def _health_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/health"


def _open_url(host: str, port: int) -> bool:
    if os.getenv("MATERIEL_NO_BROWSER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return bool(webbrowser.open(f"http://{browser_host}:{port}/", new=2))


def _bind_server_socket(host: str, preferred_port: int) -> socket.socket:
    addresses = socket.getaddrinfo(host, preferred_port, type=socket.SOCK_STREAM)
    last_error = None
    for family, socktype, protocol, _canonical_name, address in addresses:
        for port in (preferred_port, 0) if preferred_port else (0,):
            server_socket = socket.socket(family, socktype, protocol)
            try:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    server_socket.setsockopt(
                        socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                    )
                candidate = list(address)
                candidate[1] = port
                server_socket.bind(tuple(candidate))
                server_socket.listen(socket.SOMAXCONN)
                server_socket.setblocking(False)
                return server_socket
            except OSError as exc:
                last_error = exc
                server_socket.close()
                if port == 0:
                    break
    if last_error:
        raise last_error
    raise OSError(f"Could not bind a local server socket for {host}.")


def _health_ready(host: str, port: int, server_thread: threading.Thread, timeout: int = 45) -> bool:
    deadline = time.monotonic() + timeout
    url = _health_url(host, port)
    while time.monotonic() < deadline:
        if not server_thread.is_alive():
            return False
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    return False


def _write_port_file(path: Path, port: int) -> None:
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(f"{port}\n", encoding="ascii")
    os.replace(temporary_path, path)


def _open_existing_instance(data_dir: Path, identity: str) -> bool:
    port_file = data_dir / f"server-{identity}.port"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            port = int(port_file.read_text(encoding="ascii").strip())
            with urllib.request.urlopen(_health_url("127.0.0.1", port), timeout=1) as response:
                if response.status == 200:
                    if not _open_url("127.0.0.1", port):
                        _show_fatal_error(
                            RuntimeError(f"تعذر فتح المتصفح. افتح هذا الرابط يدويًا: http://127.0.0.1:{port}/"),
                            data_dir / "logs" / "error.log",
                        )
                    return True
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(0.2)
    return False


def _shutdown_event_name(identity: str) -> str:
    return f"Local\\{identity}-shutdown"


def _request_shutdown(identity: str) -> bool:
    kernel32 = _kernel32()
    event_handle = kernel32.OpenEventW(_EVENT_MODIFY_STATE, False, _shutdown_event_name(identity))
    if not event_handle:
        return False
    try:
        if not kernel32.SetEvent(event_handle):
            raise ctypes.WinError()
        return True
    finally:
        kernel32.CloseHandle(event_handle)


def _run_packaged_windows() -> int:
    import uvicorn

    from app.core.config import packaged_data_directory, settings
    from app.core.logging import configure_logging, get_logger, shutdown_logging
    from app.core.storage import migrate_packaged_uploads

    data_dir = packaged_data_directory()
    data_dir.mkdir(parents=True, exist_ok=True)
    identity = _identity()
    if "--shutdown" in sys.argv[1:]:
        _request_shutdown(identity)
        return 0

    kernel32 = _kernel32()
    mutex_name = f"Local\\{identity}"
    ctypes.set_last_error(0)
    mutex_handle = kernel32.CreateMutexW(None, True, mutex_name)
    if not mutex_handle:
        raise ctypes.WinError()
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        try:
            if not _open_existing_instance(data_dir, identity):
                raise RuntimeError(
                    "تعذر الاتصال بالنسخة المفتوحة. أغلقها من أيقونة Materiel بجانب الساعة ثم أعد المحاولة."
                )
            return 0
        finally:
            kernel32.CloseHandle(mutex_handle)

    logger = get_logger("run_web")
    server = None
    server_thread = None
    tray_icon = None
    server_socket = None
    event_handle = None
    port_file = data_dir / f"server-{identity}.port"
    try:
        configure_logging()
        logger.info("Starting packaged Materiel; version=%s", _release_version())
        migrate_packaged_uploads()
        event_handle = kernel32.CreateEventW(
            None, True, False, _shutdown_event_name(identity)
        )
        if not event_handle:
            raise ctypes.WinError()

        server_socket = _bind_server_socket(settings.HOST, settings.PORT)
        port = int(server_socket.getsockname()[1])
        config = uvicorn.Config(
            "web.main:app",
            host=settings.HOST,
            port=port,
            reload=False,
            log_config=None,
            access_log=False,
        )
        server = uvicorn.Server(config)
        server_thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [server_socket]},
            name="materiel-web-server",
            daemon=True,
        )
        server_thread.start()
        logger.info("Waiting for local server health check; port=%d", port)
        if not _health_ready(settings.HOST, port, server_thread):
            server.should_exit = True
            server_thread.join(timeout=15)
            raise RuntimeError(
                f"تعذر بدء خادم Materiel على المنفذ {port}. راجع سجل الأخطاء."
            )

        _write_port_file(port_file, port)
        logger.info("Local server ready; host=%s port=%d", settings.HOST, port)
        if os.getenv("MATERIEL_NO_BROWSER", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            logger.info("Automatic browser launch disabled by environment.")
        elif _open_url(settings.HOST, port):
            logger.info("Opened Materiel in the default browser.")
        else:
            logger.error("Could not open the default browser; url=http://127.0.0.1:%d/", port)
            _show_fatal_error(
                RuntimeError(
                    f"تعذر فتح المتصفح تلقائيًا. افتح الرابط يدويًا: http://127.0.0.1:{port}/"
                ),
                Path(settings.LOG_DIR) / "error.log",
            )

        import pystray
        from PIL import Image, ImageDraw

        icon_image = Image.new("RGB", (64, 64), "#397A54")
        draw = ImageDraw.Draw(icon_image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=12, fill="#ffffff")
        draw.text((19, 17), "M", fill="#397A54")
        def stop_from_tray(_icon, _item) -> None:
            kernel32.SetEvent(event_handle)
            _icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem(
                "فتح Materiel",
                lambda _icon, _item: _open_url(settings.HOST, port),
                default=True,
            ),
            pystray.MenuItem(
                "إيقاف Materiel",
                stop_from_tray,
            ),
        )
        tray_icon = pystray.Icon("Materiel", icon_image, "تسيير ومحاسبة العتاد", menu)

        def watch_shutdown_event() -> None:
            while server_thread.is_alive():
                result = kernel32.WaitForSingleObject(event_handle, 250)
                if result == _WAIT_OBJECT_0:
                    server.should_exit = True
                    if tray_icon:
                        tray_icon.stop()
                    return
                if result != _WAIT_TIMEOUT:
                    logger.error("Unexpected shutdown event wait result: %s", result)
                    server.should_exit = True
                    if tray_icon:
                        tray_icon.stop()
                    return

        threading.Thread(
            target=watch_shutdown_event,
            name="materiel-shutdown-monitor",
            daemon=True,
        ).start()
        tray_icon.run()
        server.should_exit = True
        server_thread.join(timeout=30)
        if server_thread.is_alive():
            raise RuntimeError("تعذر إيقاف خادم Materiel بأمان خلال المهلة المحددة.")
        logger.info("Packaged application stopped cleanly.")
        return 0
    finally:
        if server is not None:
            server.should_exit = True
        if server_thread is not None and server_thread.is_alive():
            server_thread.join(timeout=30)
        if tray_icon is not None:
            try:
                tray_icon.stop()
            except Exception:
                logger.exception("Could not stop the system-tray icon cleanly.")
        if server_socket is not None:
            try:
                server_socket.close()
            except OSError:
                logger.exception("Could not close the local server socket.")
        if event_handle:
            kernel32.CloseHandle(event_handle)
        try:
            port_file.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove the packaged server port file.")
        shutdown_logging()
        kernel32.ReleaseMutex(mutex_handle)
        kernel32.CloseHandle(mutex_handle)


def _release_version() -> str:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent / "_internal"))
    config_path = bundle_root / "splash-screen" / "config.json"
    try:
        return str(json.loads(config_path.read_text(encoding="utf-8")).get("version", "unknown"))
    except (OSError, ValueError, TypeError):
        return "unknown"


def _run_source() -> int:
    import uvicorn

    from app.core.config import settings
    from app.core.storage import migrate_packaged_uploads

    migrate_packaged_uploads()
    uvicorn.run(
        "web.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.UVICORN_RELOAD,
        reload_dirs=settings.UVICORN_RELOAD_DIRS if settings.UVICORN_RELOAD else None,
    )
    return 0


def main() -> int:
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return _run_packaged_windows()
    return _run_source()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        error_log = _write_fatal_error(exc)
        _show_fatal_error(exc, error_log)
        raise SystemExit(1) from exc
