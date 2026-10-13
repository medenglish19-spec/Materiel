from datetime import date
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.users.models import User
from app.modules.spare_parts_requests.models import SparePartRequest
from app.modules.spare_parts_requests import services as spare_request_services
from app.modules.spare_parts_requests.models import SparePartRequestItem
from app.modules.spare_parts_movements.models import SparePartMovementDocument, SparePartMovementItem
from app.modules.spare_parts_movements import services as movement_services
from .models import Fault, Repair, Technician, TechnicianIntervention, SparePart, RepairPart
from app.modules.equipment.models import Equipment
from .services import dashboard_stats, technician_stats, technician_detail_analysis, part_usage_stats, equipment_fault_stats, list_repairs

router = APIRouter()
templates = get_module_templates("app/modules/faults_repairs/templates")

@router.get("/faults-repairs", response_class=HTMLResponse)
def faults_repairs_home(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stats = dashboard_stats(db)
    faults = db.query(Fault).options(joinedload(Fault.equipment)).order_by(Fault.reported_date.desc(), Fault.id.desc()).limit(20).all()
    return templates.TemplateResponse(request=request, name="faults_repairs_dashboard.html", context={"request": request, "user": user, "stats": stats, "faults": faults})

@router.get("/faults-repairs/faults", response_class=HTMLResponse)
def faults_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    faults = db.query(Fault).options(joinedload(Fault.equipment), joinedload(Fault.repairs)).order_by(Fault.reported_date.desc(), Fault.id.desc()).all()
    fault_ids = [f.id for f in faults]
    repair_to_fault = {
        repair.id: fault.id
        for fault in faults
        for repair in fault.repairs
    }
    repair_ids = list(repair_to_fault)
    spare_requests = (
        db.query(SparePartRequest)
        .options(
            joinedload(SparePartRequest.items),
            joinedload(SparePartRequest.repair).joinedload(Repair.fault),
        )
        .filter(
            or_(
                (SparePartRequest.source_type == "fault") & SparePartRequest.fault_id.in_(fault_ids),
                (SparePartRequest.source_type == "repair") & SparePartRequest.repair_id.in_(repair_ids),
            )
        )
        .order_by(SparePartRequest.request_date.desc(), SparePartRequest.id.desc())
        .all()
        if fault_ids else []
    )
    spare_request_services.refresh_request_statuses(db, spare_requests)
    spare_requests_by_fault = {}
    for request_item in spare_requests:
        fault_id = request_item.fault_id
        if request_item.source_type == "repair" and request_item.repair:
            fault_id = request_item.repair.fault_id
        if fault_id in fault_ids:
            spare_requests_by_fault.setdefault(fault_id, []).append(request_item)
    equipment = db.query(Equipment).order_by(Equipment.registration_number, Equipment.asset_code).all()
    return templates.TemplateResponse(request=request, name="faults.html", context={
        "request": request,
        "user": user,
        "faults": faults,
        "equipment": equipment,
        "spare_requests_by_fault": spare_requests_by_fault,
    })

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
    repair_ids = [repair.id for repair in fault.repairs]
    spare_query = db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items),
        joinedload(SparePartRequest.repair),
    ).filter(
        or_(
            (SparePartRequest.source_type == "fault") & (SparePartRequest.fault_id == fault.id),
            (SparePartRequest.source_type == "repair") & SparePartRequest.repair_id.in_(repair_ids),
        )
    )
    spare_requests = spare_query.all() if repair_ids else db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items)
    ).filter(
        SparePartRequest.source_type == "fault",
        SparePartRequest.fault_id == fault.id,
    ).all()
    spare_request_services.refresh_request_statuses(db, spare_requests)
    waiting_for_parts = any(
        req.status in {"pending", "approved"}
        and any(item.received_quantity < item.requested_quantity for item in req.items)
        for req in spare_requests
    )
    active_repair = next((repair for repair in fault.repairs if repair.status == "in_progress"), None)
    return templates.TemplateResponse(request=request, name="fault_detail.html", context={
        "request": request,
        "user": user,
        "fault": fault,
        "technicians": technicians,
        "parts": parts,
        "active_repair": active_repair,
        "waiting_for_parts": waiting_for_parts,
    })

@router.get("/faults-repairs/repairs", response_class=HTMLResponse)
def repairs_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    repairs = list_repairs(db)
    return templates.TemplateResponse(request=request, name="repairs.html", context={"request": request, "user": user, "repairs": repairs})

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
    spare_requests = db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items),
    ).filter(
        SparePartRequest.source_type == "repair",
        SparePartRequest.repair_id == repair.id,
    ).order_by(SparePartRequest.request_date.desc(), SparePartRequest.id.desc()).all()
    spare_request_services.refresh_request_statuses(db, spare_requests)
    request_items = [item for req in spare_requests for item in req.items]
    balances = {item.id: movement_services.history(db, item.id)["balances"] for item in request_items}
    item_ids = [item.id for item in request_items]
    distribution_lines = db.query(SparePartMovementItem).options(
        joinedload(SparePartMovementItem.request_item).joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartMovementItem.document),
    ).join(SparePartMovementDocument).filter(
        SparePartMovementItem.request_item_id.in_(item_ids),
        SparePartMovementDocument.document_type == "distribution",
    ).order_by(SparePartMovementDocument.document_date.desc(), SparePartMovementDocument.id.desc()).all() if item_ids else []
    distribution_by_item = {}
    for line in distribution_lines:
        distribution_by_item.setdefault(line.request_item_id, {
            "item": line.request_item,
            "net_quantity": balances[line.request_item_id]["distributed"],
            "documents": [],
        })["documents"].append(f"{line.document.document_number} ({line.quantity})")
    distribution_rows = list(distribution_by_item.values())
    repair_history = db.query(Repair).join(Fault, Repair.fault_id == Fault.id).filter(
        Fault.equipment_id == repair.fault.equipment_id,
    ).order_by(Repair.repair_start_date.asc(), Repair.repair_date.asc(), Repair.id.asc()).all()
    current_repair = next((item for item in repair_history if item.status == "in_progress"), None)
    if current_repair is None and repair_history:
        current_repair = repair_history[-1]
    return templates.TemplateResponse(request=request, name="repair_detail.html", context={
        "request": request, "user": user, "repair": repair, "technicians": technicians,
        "parts": parts, "spare_requests": spare_requests,
        "repair_history": repair_history,
        "current_repair_id": current_repair.id if current_repair else None,
        "part_balances": balances, "distribution_lines": distribution_lines,
        "distribution_rows": distribution_rows,
        "today": date.today().isoformat(),
        "waiting_for_parts": any(req.status in {"pending", "approved"} and any(
            item.received_quantity < item.requested_quantity for item in req.items
        ) for req in spare_requests),
    })

@router.get("/faults-repairs/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="analytics.html", context={
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
    return templates.TemplateResponse(request=request, name="technicians.html", context={"request": request, "user": user, "technicians": technicians, "stats_by_id": stats_by_id})

@router.get("/faults-repairs/technicians/{technician_id}", response_class=HTMLResponse)
def technician_detail_page(technician_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    analysis = technician_detail_analysis(db, technician_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="الفني غير موجود")
    return templates.TemplateResponse(request=request, name="technician_detail.html", context={"request": request, "user": user, "analysis": analysis})

