from pathlib import Path
import json
import sys

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).resolve().parent

# collect_submodules runs before Analysis applies pathex, so make local project
# packages discoverable even when the build script is launched from elsewhere.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def data_tree(source: Path, destination: str, *, exclude_uploads: bool = False):
    entries = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part == "__pycache__" for part in relative.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        if exclude_uploads and relative.parts and relative.parts[0] == "uploads":
            continue
        target = Path(destination) / relative.parent
        entries.append((str(path), str(target)))
    return entries


datas = []
datas += data_tree(ROOT / "app" / "modules", "app/modules")
datas += data_tree(ROOT / "web" / "templates", "web/templates")
datas += data_tree(ROOT / "static", "static", exclude_uploads=True)
datas += data_tree(ROOT / "migrations", "migrations")
datas.append((str(ROOT / "alembic.ini"), "."))

# Splash text and logo are release assets. They are installed with the protected
# application bundle, never copied into the user's writable data directory.
SPLASH_DIR = ROOT / "splash-screen"
SPLASH_CONFIG = SPLASH_DIR / "config.json"
branding = json.loads(SPLASH_CONFIG.read_text(encoding="utf-8"))
logo_name = branding.get("logo_file", "")
if not logo_name or Path(logo_name).name != logo_name:
    raise ValueError("splash-screen/config.json must set logo_file to a file in splash-screen")
logo_path = SPLASH_DIR / logo_name
if not logo_path.is_file():
    raise FileNotFoundError(f"Configured splash logo is missing: {logo_path}")
datas.append((str(SPLASH_CONFIG), "splash-screen"))
datas.append((str(logo_path), "splash-screen"))

hiddenimports = sorted(set(
    collect_submodules("app")
    + collect_submodules("web")
    + collect_submodules("alembic")
    + collect_submodules("uvicorn")
    + collect_submodules("passlib.handlers")
    + collect_submodules("jose")
))

a = Analysis(
    [str(ROOT / "run_web.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "playwright"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Materiel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Materiel",
)
