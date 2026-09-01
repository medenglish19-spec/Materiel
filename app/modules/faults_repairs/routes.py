from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.users.models import User
from .models import Fault, Repair, Technician, TechnicianIntervention, SparePart, RepairPart
from .services import dashboard_stats, technician_stats, part_usage_stats, list_repairs

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
    return templates.TemplateResponse("faults.html", {"request": request, "user": user, "faults": faults})

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
        return templates.TemplateResponse("not_found.html", {"request": request, "user": user}, status_code=404)
    return templates.TemplateResponse("repair_detail.html", {"request": request, "user": user, "repair": repair})

@router.get("/faults-repairs/technicians", response_class=HTMLResponse)
def technicians_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    technicians = db.query(Technician).order_by(Technician.full_name).all()
    stats = technician_stats(db)
    stats_by_id = {x["technician_id"]: x for x in stats}
    return templates.TemplateResponse("technicians.html", {"request": request, "user": user, "technicians": technicians, "stats_by_id": stats_by_id})

@router.get("/faults-repairs/spare-parts", response_class=HTMLResponse)
def spare_parts_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parts = db.query(SparePart).order_by(SparePart.name).all()
    usage = part_usage_stats(db)
    usage_by_number = {x["part_number"]: x for x in usage}
    return templates.TemplateResponse("spare_parts.html", {"request": request, "user": user, "parts": parts, "usage_by_number": usage_by_number})
