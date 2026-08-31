from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from . import services
from .models import SparePart
from .schemas import FaultCreate, FaultUpdate, FaultStatusUpdate, FaultOut, RepairCreate, RepairOut, SparePartCreate, SparePartUpdate, SparePartOut, RepairPartCreate, RepairPartOut

router = APIRouter(prefix="/api/faults-repairs")


@router.get("/faults", response_model=list[FaultOut])
def faults(equipment_id: int | None = None, status: str | None = None, severity: str | None = None, start_date: date | None = None, end_date: date | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return services.list_faults(db, equipment_id, status, severity, start_date, end_date)


@router.post("/faults", response_model=FaultOut, status_code=201)
def create_fault(data: FaultCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try: return services.create_fault(db, data, user.id)
    except ValueError as e: raise HTTPException(400, str(e))


@router.patch("/faults/{fault_id}", response_model=FaultOut)
def update_fault(fault_id: int, data: FaultUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_fault(db, fault_id)
    if not obj: raise HTTPException(404, "العطل غير موجود")
    try: return services.update_fault(db, obj, data)
    except ValueError as e: raise HTTPException(400, str(e))


@router.patch("/faults/{fault_id}/status", response_model=FaultOut)
def change_status(fault_id: int, data: FaultStatusUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_fault(db, fault_id)
    if not obj: raise HTTPException(404, "العطل غير موجود")
    try: return services.change_fault_status(db, obj, data.status)
    except ValueError as e: raise HTTPException(400, str(e))


@router.post("/repairs", response_model=RepairOut, status_code=201)
def create_repair(data: RepairCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try: return services.create_repair(db, data, user.id)
    except ValueError as e: raise HTTPException(400, str(e))


@router.post("/spare-parts", response_model=SparePartOut, status_code=201)
def create_part(data: SparePartCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try: return services.create_spare_part(db, data)
    except ValueError as e: raise HTTPException(400, str(e))


@router.patch("/spare-parts/{part_id}", response_model=SparePartOut)
def update_part(part_id: int, data: SparePartUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePart).filter(SparePart.id == part_id).first()
    if not obj: raise HTTPException(404, "قطعة الغيار غير موجودة")
    try: return services.update_spare_part(db, obj, data)
    except ValueError as e: raise HTTPException(400, str(e))


@router.post("/repair-parts", response_model=RepairPartOut, status_code=201)
def add_part(data: RepairPartCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try: return services.add_repair_part(db, data)
    except ValueError as e: raise HTTPException(400, str(e))


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"summary": services.dashboard_stats(db), "technicians": services.technician_stats(db), "parts": services.part_usage_stats(db), "equipment": services.equipment_fault_stats(db)}


@router.get("/technicians", response_model=list[__import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianOut"]).TechnicianOut])
def technicians(active_only: bool = False, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return services.list_technicians(db, active_only)

@router.post("/technicians", response_model=__import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianOut"]).TechnicianOut, status_code=201)
def create_technician(data: __import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianCreate"]).TechnicianCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try: return services.create_technician(db, data)
    except Exception as e: raise HTTPException(400, str(e))

@router.patch("/technicians/{technician_id}", response_model=__import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianOut"]).TechnicianOut)
def update_technician(technician_id: int, data: __import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianUpdate"]).TechnicianUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(services.Technician).filter(services.Technician.id == technician_id).first()
    if not obj: raise HTTPException(404, "الفني غير موجود")
    return services.update_technician(db, obj, data)

@router.post("/technician-interventions", response_model=__import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianInterventionOut"]).TechnicianInterventionOut, status_code=201)
def add_intervention(data: __import__("app.modules.faults_repairs.schemas", fromlist=["TechnicianInterventionCreate"]).TechnicianInterventionCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try: return services.add_technician_intervention(db, data)
    except ValueError as e: raise HTTPException(400, str(e))

@router.get("/technicians/{technician_id}/statistics")
def technician_statistics(technician_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    result = services.technician_detail_stats(db, technician_id)
    if not result: raise HTTPException(404, "الفني غير موجود")
    return result
