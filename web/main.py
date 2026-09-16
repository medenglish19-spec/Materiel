from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.security import decode_access_token
from app.database.init_db import create_default_admin, init_db
from app.modules.dashboard.router import router as dashboard_router
from app.modules.equipment.router import router as equipment_router
from app.modules.equipment_maintenance.router import router as equipment_maintenance_router
from app.modules.equipment_types.router import router as equipment_types_router
from app.modules.faults_repairs.router import router as faults_repairs_router
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
MASTER_DATA_SCRIPT = '<script src="/static/js/master-data-tree.js"></script>'


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        create_default_admin()
        yield

    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(HTTPException)
    async def html_http_exception_handler(request: Request, exc: HTTPException):
        accept=request.headers.get("accept", "")
        referer=request.headers.get("referer")
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

        content_type = response.headers.get("content-type", "")
        if request.url.path == "/equipment-types" and "text/html" in content_type:
            body = b"".join([chunk async for chunk in response.body_iterator])
            text = body.decode("utf-8")
            if MASTER_DATA_SCRIPT not in text:
                marker = "</body>" if "</body>" in text else "</html>"
                if marker in text:
                    text = text.replace(marker, MASTER_DATA_SCRIPT + marker, 1)
            headers = dict(response.headers)
            headers.pop("content-length", None)
            response = HTMLResponse(content=text, status_code=response.status_code, headers=headers)

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
