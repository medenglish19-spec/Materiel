from typing import Optional
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment import services
from app.modules.equipment.analytics import build_capacity_readiness_analysis, build_utilization_analysis
from app.modules.equipment.operational_analysis import build_operational_analysis
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentOut, EquipmentUpdate
from app.modules.equipment_types import services as type_services
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.equipment_types.models import EquipmentModelSpecValue
from app.modules.users.models import User
from app.modules.meter_readings import services as meter_services
from app.modules.meter_readings.models import MeterReading
from app.modules.missions.models import Mission
from app.modules.fuel.models import FuelRecord
from app.modules.faults_repairs.models import Fault, Repair
from app.modules.maintenance.models import MaintenanceRecord
from app.modules.meter_readings.audit import MeterReadingChange, utc_now
from app.modules.tires import services as tire_services
from app.modules.batteries import services as battery_services
router = APIRouter(); templates = get_module_templates("app/modules/equipment/templates")
@router.get("/equipment", response_class=HTMLResponse)
def equipment_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = services.list_equipment(db)
    operational_statuses = services.effective_operational_statuses(db, items)
    types = type_services.list_user_types(db)

    # --- إضافة: بيانات الخصائص الحرّة للفلترة في /equipment ---
    spec_definitions = type_services.list_spec_definitions(db)
    spec_definitions_data = [
        {"id": d.id, "name": d.name, "data_type": d.data_type, "unit": d.unit, "options": d.options}
        for d in spec_definitions
    ]

    model_ids = {item.equipment_model_id for item in items if item.equipment_model_id is not None}
    specs_by_model: dict[int, dict[int, str]] = {}
    if model_ids:
        rows = db.query(EquipmentModelSpecValue).filter(EquipmentModelSpecValue.equipment_model_id.in_(model_ids)).all()
        for row in rows:
            specs_by_model.setdefault(row.equipment_model_id, {})[row.spec_definition_id] = row.value
    equipment_specs_map = {
        item.id: specs_by_model.get(item.equipment_model_id, {}) for item in items
    }
    # --- نهاية الإضافة ---

    return templates.TemplateResponse(request=request, name="equipment_list.html", context={
        "request": request, "items": items, "types": types, "user": current_user,
        "spec_definitions_data": spec_definitions_data,
        "equipment_specs_map": equipment_specs_map,
        "operational_statuses": operational_statuses,
    })
@router.get("/equipment/analysis", response_class=HTMLResponse)
def equipment_analysis_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = (db.query(Equipment).options(joinedload(Equipment.equipment_type).joinedload(EquipmentType.category), joinedload(Equipment.equipment_model)).order_by(Equipment.id).all())
    analysis = build_capacity_readiness_analysis(items)
    equipment_ids = [x.id for x in items]
    meter_readings = db.query(MeterReading).filter(MeterReading.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    missions = db.query(Mission).filter(Mission.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    fuel_records = db.query(FuelRecord).filter(FuelRecord.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    faults = db.query(Fault).filter(Fault.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    maintenance_records = db.query(MaintenanceRecord).filter(MaintenanceRecord.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    utilization = build_utilization_analysis(items, meter_readings, missions, fuel_records)
    repairs = db.query(Repair).join(Fault, Repair.fault_id == Fault.id).filter(Fault.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    operational = build_operational_analysis(items, faults, maintenance_records, repairs=repairs, utilization=utilization)
    return templates.TemplateResponse(request=request, name="equipment_analysis.html", context={"request": request, "user": current_user, **analysis, "utilization": utilization, "operational": operational})

@router.get("/equipment/analysis/operational", response_class=HTMLResponse)
def equipment_operational_analysis_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = (db.query(Equipment).options(joinedload(Equipment.equipment_model), joinedload(Equipment.equipment_type)).order_by(Equipment.id).all())
    equipment_ids = [x.id for x in items]
    meter_readings = db.query(MeterReading).filter(MeterReading.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    missions = db.query(Mission).filter(Mission.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    fuel_records = db.query(FuelRecord).filter(FuelRecord.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    faults = db.query(Fault).filter(Fault.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    maintenance_records = db.query(MaintenanceRecord).filter(MaintenanceRecord.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    utilization = build_utilization_analysis(items, meter_readings, missions, fuel_records)
    repairs = db.query(Repair).join(Fault, Repair.fault_id == Fault.id).filter(Fault.equipment_id.in_(equipment_ids)).all() if equipment_ids else []
    operational = build_operational_analysis(items, faults, maintenance_records, repairs=repairs, utilization=utilization)
    return templates.TemplateResponse(request=request, name="equipment_operational_analysis.html", context={"request": request, "user": current_user, "utilization": utilization, "operational": operational})
