from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
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
from app.modules.users.router import router as users_router


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_ROOT / "static"


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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
    app.include_router(tires_router, tags=["tires"])

    @app.on_event("startup")
    def on_startup():
        init_db()
        create_default_admin()

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
