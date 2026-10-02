from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import security_warnings, settings
from app.core.logging import configure_logging, get_logger, shutdown_logging
from app.core.security import decode_access_token
from app.database.init_db import create_default_admin, init_db
from app.modules.dashboard.router import router as dashboard_router
from app.modules.equipment.router import router as equipment_router
from app.modules.equipment_maintenance.router import router as equipment_maintenance_router
from app.modules.equipment_types.router import router as equipment_types_router
from app.modules.faults_repairs.router import router as faults_repairs_router
from app.modules.spare_parts_requests.router import router as spare_parts_requests_router
from app.modules.spare_parts_requests.routes import router as spare_parts_requests_pages_router
from app.modules.faults_repairs.routes import router as faults_repairs_pages_router
from app.modules.maintenance.router import router as maintenance_router
from app.modules.meter_readings.audit_router import router as meter_reading_audit_router
from app.modules.meter_readings.router import router as meter_readings_router
from app.modules.tires.router import router as tires_router
from app.modules.batteries.router import router as batteries_router
from app.modules.fuel.router import router as fuel_router
from app.modules.missions.router import router as missions_router
from app.modules.users.router import router as users_router

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"

logger = get_logger(__name__)


def _database_file() -> str | None:
    """مسار ملف SQLite من DATABASE_URL، أو None لقاعدة غير ملفاتية."""
    prefix = "sqlite:///"
    if not settings.DATABASE_URL.startswith(prefix):
        return None
    tail = settings.DATABASE_URL[len(prefix) :]
    if tail in ("", ":memory:"):
        return None
    return tail


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_logging()
        logger.info("Starting %s (%s)", settings.APP_NAME, settings.ENV)
        init_db()
        create_default_admin()
        # تحذيرات ما قبل النشر: تُسجَّل ولا توقف الإقلاع (انظر core/config.py).
        for warning in security_warnings(_database_file()):
            logger.warning("[security] %s", warning)
        yield
        logger.info("Shutting down %s", settings.APP_NAME)
        shutdown_logging()

    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(HTTPException)
    async def html_http_exception_handler(request: Request, exc: HTTPException):
        accept=request.headers.get("accept", "")
        referer=request.headers.get("referer")
        if exc.status_code >= 500:
            logger.error("HTTP %s %s -> %s", request.method, request.url.path, exc.detail)
        elif exc.status_code >= 400:
            logger.warning("HTTP %s %s -> %s", request.method, request.url.path, exc.detail)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and "text/html" in accept and referer:
            base=str(request.base_url)
            if referer.startswith(base):
                parsed=urlsplit(referer)
                target=parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
                separator="&" if parsed.query else "?"
                detail=str(exc.detail) if exc.detail else "تعذر تنفيذ العملية. راجع البيانات وحاول مرة أخرى."
                target += separator + "notice_type=warning&notice=" + quote(detail)
                return RedirectResponse(url=target,status_code=303)
        return JSONResponse(status_code=exc.status_code,content={"detail":exc.detail},headers=exc.headers)

    @app.middleware("http")
    async def fresh_dynamic_pages(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "private, no-cache, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    app.include_router(users_router, tags=["users"])
    app.include_router(equipment_types_router, tags=["equipment_types"])
    app.include_router(equipment_router, tags=["equipment"])
    app.include_router(dashboard_router, tags=["dashboard"])
    app.include_router(meter_readings_router, tags=["meter_readings"])
    app.include_router(meter_reading_audit_router, tags=["meter_reading_operations"])
    app.include_router(maintenance_router, tags=["maintenance"])
    app.include_router(equipment_maintenance_router, tags=["equipment_maintenance"])
    app.include_router(faults_repairs_router, tags=["faults_repairs"])
    app.include_router(faults_repairs_pages_router, tags=["faults_repairs_pages"])
    app.include_router(spare_parts_requests_router, tags=["spare_parts_requests"])
    app.include_router(spare_parts_requests_pages_router, tags=["spare_parts_requests_pages"])
    app.include_router(tires_router, tags=["tires"])
    app.include_router(batteries_router, tags=["batteries"])
    app.include_router(fuel_router, tags=["fuel"])
    app.include_router(missions_router, tags=["missions"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def root(request: Request):
        token = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if token:
            payload = decode_access_token(token)
            if payload and payload.get("sub"):
                return RedirectResponse(url="/dashboard")
        return RedirectResponse(url="/login")

    return app


app = create_app()
