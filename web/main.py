from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.database.init_db import init_db, create_default_admin
from app.modules.users.router import router as users_router
from app.modules.equipment_types.router import router as equipment_types_router
from app.modules.equipment.router import router as equipment_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.meter_readings.router import router as meter_readings_router
from app.modules.meter_readings.audit_router import router as meter_reading_audit_router
from app.modules.maintenance.router import router as maintenance_router
from app.modules.equipment_maintenance.router import router as equipment_maintenance_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)
    app.mount('/static', StaticFiles(directory='static'), name='static')
    app.include_router(users_router, tags=['users'])
    app.include_router(equipment_types_router, tags=['equipment_types'])
    app.include_router(equipment_router, tags=['equipment'])
    app.include_router(dashboard_router, tags=['dashboard'])
    app.include_router(meter_readings_router, tags=['meter_readings'])
    # سجل العمليات الموحد هو المرجع الوحيد للجلسات الجماعية والتفاصيل والتراجع.
    app.include_router(meter_reading_audit_router, tags=['meter_reading_operations'])
    app.include_router(maintenance_router, tags=['maintenance'])
    app.include_router(equipment_maintenance_router, tags=['equipment_maintenance'])

    @app.on_event('startup')
    def on_startup():
        init_db()
        create_default_admin()

    @app.get('/')
    def root():
        return RedirectResponse(url='/dashboard')

    return app


app = create_app()
