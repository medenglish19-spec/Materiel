from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.users.models import User
from .models import Fault, Repair, Technician, TechnicianIntervention, SparePart, RepairPart
from app.modules.equipment.models import Equipment
from .services import dashboard_stats, technician_stats, technician_detail_analysis, part_usage_stats, equipment_fault_stats, list_repairs

router = APIRouter()
templates = get_module_templates("app/modules/faults_repairs/templates")

@router.get("/faults-repairs", response_class=HTMLResponse)
def faults_repairs_home(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stats = dashboard_stats(db)
    faults = db.query(Fault).options(joinedload(Fault.equipment)).order_by(Fault.reported_date.desc(), Fault.id.desc()).limit(20).all()
    return templates.TemplateResponse("faults_repairs_dashboard.html", {"request": request, "user": user, "stats": stats, "faults": faults})

@router.get("/faults-repairs/faults", response_class=HTMLResponse)
def faults_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    faults = db.query(Fault).options(joinedload(Fault.equipment), joinedload(Fault.repairs)).order_by(Fault.reported_date.desc(), Fault.id.desc()).all()
    equipment = db.query(Equipment).order_by(Equipment.registration_number, Equipment.asset_code).all()
    return templates.TemplateResponse("faults.html", {"request": request, "user": user, "faults": faults, "equipment": equipment})

@router.get("/faults-repairs/faults/{fault_id}", response_class=HTMLResponse)
def fault_detail_page(fault_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    fault = db.query(Fault).options(
        joinedload(Fault.equipment),
        joinedload(Fault.maintenance_record),
        joinedload(Fault.repairs),
    ).filter(Fault.id == fault_id).first()
    if not fault:
        raise HTTPException(status_code=404, detail="العطل غير موجود")
    technicians = db.query(Technician).filter(Technician.is_active == 1).order_by(Technician.full_name).all()
    parts = db.query(SparePart).order_by(SparePart.name).all()
    return templates.TemplateResponse("fault_detail.html", {"request": request, "user": user, "fault": fault, "technicians": technicians, "parts": parts})

@router.get("/faults-repairs/repairs", response_class=HTMLResponse)
def repairs_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repairs = list_repairs(db)
    return templates.TemplateResponse("repairs.html", {"request": request, "user": user, "repairs": repairs})

@router.get("/faults-repairs/repairs/{repair_id}", response_class=HTMLResponse)
def repair_detail_page(repair_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repair = db.query(Repair).options(
        joinedload(Repair.fault).joinedload(Fault.equipment),
        joinedload(Repair.technician_interventions).joinedload(TechnicianIntervention.technician),
        joinedload(Repair.consumed_parts).joinedload(RepairPart.spare_part),
    ).filter(Repair.id == repair_id).first()
    if not repair:
        raise HTTPException(status_code=404, detail="التصليح غير موجود")
    technicians = db.query(Technician).filter(Technician.is_active == 1).order_by(Technician.full_name).all()
    parts = db.query(SparePart).order_by(SparePart.name).all()
    return templates.TemplateResponse("repair_detail.html", {"request": request, "user": user, "repair": repair, "technicians": technicians, "parts": parts})

@router.get("/faults-repairs/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "user": user,
        "stats": dashboard_stats(db),
        "technicians_stats": technician_stats(db),
        "parts_stats": part_usage_stats(db),
        "equipment_stats": equipment_fault_stats(db),
    })

@router.get("/faults-repairs/technicians", response_class=HTMLResponse)
def technicians_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    technicians = db.query(Technician).order_by(Technician.full_name).all()
    stats = technician_stats(db)
    stats_by_id = {x["technician_id"]: x for x in stats}
    return templates.TemplateResponse("technicians.html", {"request": request, "user": user, "technicians": technicians, "stats_by_id": stats_by_id})

@router.get("/faults-repairs/technicians/{technician_id}", response_class=HTMLResponse)
def technician_detail_page(technician_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analysis = technician_detail_analysis(db, technician_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="الفني غير موجود")
    return templates.TemplateResponse("technician_detail.html", {"request": request, "user": user, "analysis": analysis})

@router.get("/faults-repairs/spare-parts", response_class=HTMLResponse)
def spare_parts_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parts = db.query(SparePart).order_by(SparePart.name).all()
    usage = part_usage_stats(db)
    usage_by_number = {x["part_number"]: x for x in usage}
    return templates.TemplateResponse("spare_parts.html", {"request": request, "user": user, "parts": parts, "usage_by_number": usage_by_number})
