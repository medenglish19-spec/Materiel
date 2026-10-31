"""
run_web.py
-----------
نقطة تشغيل واحدة للمشروع. الموظفون على الشبكة الداخلية يدخلون عبر:
    http://<عنوان-السيرفر>:8000

للتشغيل:
    python run_web.py
"""

import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.storage import migrate_packaged_uploads


def _prepare_packaged_directories() -> None:
    if not getattr(sys, "frozen", False):
        return
    database_url = make_url(settings.DATABASE_URL)
    if database_url.drivername.startswith("sqlite") and database_url.database not in {
        None, "", ":memory:"
    } and not database_url.database.startswith("file:"):
        Path(database_url.database).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
    migrate_packaged_uploads()


def _open_browser_when_ready() -> None:
    host = settings.HOST if settings.HOST not in {"0.0.0.0", "::"} else "127.0.0.1"
    page_url = f"http://{host}:{settings.PORT}/"
    health_url = f"http://{host}:{settings.PORT}/health"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(page_url, new=2)
                    return
        except OSError:
            time.sleep(0.4)


if __name__ == "__main__":
    _prepare_packaged_directories()
    if getattr(sys, "frozen", False) and not os.getenv("MATERIEL_NO_BROWSER"):
        threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    kwargs = {
        "app": "web.main:app",
        "host": settings.HOST,
        "port": settings.PORT,
        "reload": settings.UVICORN_RELOAD,
    }
    if settings.UVICORN_RELOAD:
        kwargs["reload_dirs"] = settings.UVICORN_RELOAD_DIRS
    uvicorn.run(**kwargs)
