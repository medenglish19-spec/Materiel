from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.maintenance.models import MaintenanceRecord
from .models import Fault, Repair, SparePart, RepairPart, Technician, TechnicianIntervention
from .schemas import FaultCreate, FaultUpdate, RepairCreate, SparePartCreate, SparePartUpdate, RepairPartCreate



ACTIVE_FAULT_STATUSES = {"open", "diagnosing", "repairing", "waiting_parts"}
TERMINAL_FAULT_STATUSES = {"repaired", "closed"}


def _latest_meter_before(db: Session, equipment_id: int, before_date: date):
    values = []
    for query in (
        db.query(func.max(MaintenanceRecord.meter_value)).filter(MaintenanceRecord.equipment_id == equipment_id, MaintenanceRecord.maintenance_date < before_date, MaintenanceRecord.meter_value.isnot(None)),
        db.query(func.max(Fault.meter_value)).filter(Fault.equipment_id == equipment_id, Fault.reported_date < before_date, Fault.meter_value.isnot(None)),
        db.query(func.max(Repair.meter_value)).join(Fault).filter(Fault.equipment_id == equipment_id, Repair.repair_date < before_date, Repair.meter_value.isnot(None)),
    ):
        value = query.scalar()
        if value is not None: values.append(value)
    return max(values) if values else None


def _validate_meter_sequence(db: Session, equipment: Equipment, meter_value, event_date: date):
    if meter_value is None: return
    if equipment.current_odometer is not None and meter_value > equipment.current_odometer:
        raise ValueError("العداد يتجاوز عداد العتاد الحالي")
    previous = _latest_meter_before(db, equipment.id, event_date)
    if previous is not None and meter_value < previous:
        raise ValueError("العداد أقل من قراءة سابقة لنفس العتاد")


def _sync_equipment_from_faults(db: Session, equipment_id: int):
    """Synchronize equipment technical and operational state with active faults/repairs."""
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        return
    external_repair = db.query(Repair).join(Fault).filter(
        Fault.equipment_id == equipment_id,
        Repair.workshop_type == "external",
        Repair.status == "in_progress",
    ).first()
    internal_repair = db.query(Repair).join(Fault).filter(
        Fault.equipment_id == equipment_id,
        Repair.workshop_type == "internal",
        Repair.status == "in_progress",
    ).first()
    # A registered fault does not automatically make equipment unusable.
    # Only a fault explicitly marked as prohibiting exploitation makes it broken.
    prohibited_fault = db.query(Fault).filter(
        Fault.equipment_id == equipment_id,
        Fault.status.in_(ACTIVE_FAULT_STATUSES),
        Fault.exploitation_impact == "prohibited",
    ).first()
    limited_fault = db.query(Fault).filter(
        Fault.equipment_id == equipment_id,
        Fault.status.in_(ACTIVE_FAULT_STATUSES),
        Fault.exploitation_impact == "limited",
    ).first()

    if prohibited_fault:
        equipment.technical_condition = "broken"
    elif limited_fault:
        equipment.technical_condition = "ready_restricted"
    else:
        equipment.technical_condition = "ready"

    # Operational status describes where/how the equipment is being used.
    # A repair in progress takes precedence over the normal operational status.
    if external_repair:
        equipment.operational_status = "in_external_workshop"
    elif internal_repair:
        equipment.operational_status = "in_maintenance"
    elif equipment.operational_status in {"in_maintenance", "in_external_workshop"}:
        equipment.operational_status = "available"
    return equipment


FAULT_TRANSITIONS = {
    "open": {"diagnosing"},
    "diagnosing": {"repairing", "waiting_parts"},
    "repairing": {"waiting_parts", "repaired"},
    "waiting_parts": {"repairing", "repaired"},
    "repaired": {"closed"},
    "closed": set(),
}


def get_fault(db: Session, fault_id: int):
    return db.query(Fault).options(joinedload(Fault.equipment), joinedload(Fault.repairs)).filter(Fault.id == fault_id).first()


def list_faults(db: Session, equipment_id=None, status=None, severity=None, start_date=None, end_date=None):
    q = db.query(Fault).options(joinedload(Fault.equipment))
    if equipment_id: q = q.filter(Fault.equipment_id == equipment_id)
    if status: q = q.filter(Fault.status == status)
    if severity: q = q.filter(Fault.severity == severity)
    if start_date: q = q.filter(Fault.reported_date >= start_date)
    if end_date: q = q.filter(Fault.reported_date <= end_date)
    return q.order_by(Fault.reported_date.desc(), Fault.id.desc()).all()


def create_fault(db: Session, data: FaultCreate, user_id: Optional[int] = None):
    equipment = db.query(Equipment).filter(Equipment.id == data.equipment_id).first()
    if not equipment: raise ValueError("العتاد غير موجود")
    if data.maintenance_record_id:
        record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == data.maintenance_record_id, MaintenanceRecord.equipment_id == data.equipment_id).first()
        if not record: raise ValueError("سجل الصيانة غير موجود لهذا العتاد")
    if data.reported_date > date.today(): raise ValueError("لا يمكن تسجيل عطل بتاريخ مستقبلي")
    _validate_meter_sequence(db, equipment, data.meter_value, data.reported_date)
    obj = Fault(**data.model_dump(), status="open", created_by_id=user_id)
    db.add(obj)
    db.flush()
    _sync_equipment_from_faults(db, obj.equipment_id)
    db.commit()
    db.refresh(obj)
    return obj


def update_fault(db: Session, obj: Fault, data: FaultUpdate):
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    if obj.reported_date > date.today(): raise ValueError("لا يمكن تسجيل عطل بتاريخ مستقبلي")
    equipment = db.query(Equipment).filter(Equipment.id == obj.equipment_id).first()
    _validate_meter_sequence(db, equipment, obj.meter_value, obj.reported_date)
    _sync_equipment_from_faults(db, obj.equipment_id)
    db.commit(); db.refresh(obj); return obj


def change_fault_status(db: Session, obj: Fault, new_status: str):
    allowed = FAULT_TRANSITIONS.get(obj.status, set())
    if new_status == obj.status: return obj
    if new_status not in allowed: raise ValueError(f"لا يمكن نقل حالة العطل من {obj.status} إلى {new_status}")
    obj.status = new_status
    _sync_equipment_from_faults(db, obj.equipment_id)
    db.commit()
    db.refresh(obj)
    return obj


def create_repair(db: Session, data: RepairCreate, user_id=None):
    fault = db.query(Fault).filter(Fault.id == data.fault_id).first()
    if not fault: raise ValueError("العطل غير موجود")
    if data.repair_date > date.today(): raise ValueError("لا يمكن تسجيل إصلاح بتاريخ مستقبلي")
    equipment = db.query(Equipment).join(Fault, Fault.equipment_id == Equipment.id).filter(Fault.id == data.fault_id).first()
    if not equipment: raise ValueError("العتاد المرتبط بالعطل غير موجود")
    _validate_meter_sequence(db, equipment, data.meter_value, data.repair_date)
    if data.workshop_type == "external" and not data.external_dispatch_document:
        raise ValueError("وثيقة إرسال العتاد للورشة الخارجية إلزامية")
    if fault.status not in {"diagnosing", "repairing", "waiting_parts"}:
        raise ValueError("لا يمكن تسجيل تصليح قبل أن يكون العطل قيد التشخيص أو الإصلاح أو بانتظار قطع الغيار")
    obj = Repair(**data.model_dump(), created_by_id=user_id)
    db.add(obj)
    db.flush()
    if obj.status == "in_progress":
        fault.status = "repairing"
    elif obj.status == "completed":
        fault.status = "repaired"
    _sync_equipment_from_faults(db, fault.equipment_id)
    db.commit()
    db.refresh(obj)
    return obj


def create_spare_part(db: Session, data: SparePartCreate):
    obj = SparePart(**data.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return obj


def update_spare_part(db: Session, obj: SparePart, data: SparePartUpdate):
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(obj,k,v)
    db.commit(); db.refresh(obj); return obj


def add_repair_part(db: Session, data: RepairPartCreate):
    repair = db.query(Repair).filter(Repair.id == data.repair_id).first()
    part = db.query(SparePart).filter(SparePart.id == data.spare_part_id).first()
    if not repair: raise ValueError("التصليح غير موجود")
    if not part: raise ValueError("قطعة الغيار غير موجودة")
    obj = RepairPart(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj); return obj


def dashboard_stats(db: Session):
    def count(*criteria): return db.query(func.count(Fault.id)).filter(*criteria).scalar()
    total = count()
    by_status = dict(db.query(Fault.status, func.count(Fault.id)).group_by(Fault.status).all())
    by_severity = dict(db.query(Fault.severity, func.count(Fault.id)).group_by(Fault.severity).all())
    repairs = db.query(Repair).count()
    internal_open = db.query(Repair).join(Fault).filter(Repair.workshop_type == "internal", Repair.status == "in_progress").count()
    external_open = db.query(Repair).join(Fault).filter(Repair.workshop_type == "external", Repair.status == "in_progress").count()
    monthly_faults = db.query(Fault).filter(Fault.reported_date >= date.today().replace(day=1)).count()
    hours = db.query(func.coalesce(func.sum(TechnicianIntervention.hours), 0)).scalar()
    parts = db.query(func.coalesce(func.sum(RepairPart.quantity), 0)).scalar()
    return {"faults_total": total, "faults_by_status": by_status, "faults_by_severity": by_severity,
            "repairs_total": repairs, "labor_hours": hours, "parts_consumed": parts,
            "internal_repairs_in_progress": internal_open, "external_repairs_in_progress": external_open,
            "faults_this_month": monthly_faults}


def technician_stats(db: Session):
    rows = db.query(
        Technician.id, Technician.full_name, Technician.specialization,
        func.count(TechnicianIntervention.id),
        func.coalesce(func.sum(TechnicianIntervention.hours), 0),
    ).outerjoin(
        TechnicianIntervention, TechnicianIntervention.technician_id == Technician.id
    ).group_by(Technician.id).order_by(
        func.count(TechnicianIntervention.id).desc()
    ).all()
    return [{"technician_id": i, "technician": n, "specialization": s,
             "interventions": int(c or 0), "labor_hours": float(h or 0)}
            for i,n,s,c,h in rows]


def part_usage_stats(db: Session):
    rows = db.query(SparePart.part_number, SparePart.name, func.sum(RepairPart.quantity)).join(RepairPart, RepairPart.spare_part_id == SparePart.id).group_by(SparePart.id).order_by(func.sum(RepairPart.quantity).desc()).all()
    return [{"part_number": n, "name": name, "quantity": float(q or 0)} for n,name,q in rows]


def equipment_fault_stats(db: Session):
    rows = db.query(Equipment.id, Equipment.asset_code, Equipment.registration_number, func.count(Fault.id)).join(Fault, Fault.equipment_id == Equipment.id).group_by(Equipment.id).order_by(func.count(Fault.id).desc()).all()
    return [{"equipment_id": i, "asset_code": a, "registration_number": r, "faults": int(c)} for i,a,r,c in rows]


def create_technician(db: Session, data):
    obj = Technician(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj); return obj

def list_technicians(db: Session, active_only=False):
    q = db.query(Technician)
    if active_only: q = q.filter(Technician.is_active == 1)
    return q.order_by(Technician.full_name).all()

def update_technician(db: Session, obj, data):
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(obj,k,v)
    db.commit(); db.refresh(obj); return obj

def add_technician_intervention(db: Session, data):
    repair = db.query(Repair).filter(Repair.id == data.repair_id).first()
    tech = db.query(Technician).filter(Technician.id == data.technician_id).first()
    if not repair: raise ValueError("التصليح غير موجود")
    if not tech: raise ValueError("الفني غير موجود")
    if not tech.is_active: raise ValueError("الفني غير نشط")
    obj = TechnicianIntervention(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj); return obj

def technician_detail_stats(db: Session, technician_id: int):
    row = db.query(
        Technician.id, Technician.full_name, Technician.specialization,
        func.count(TechnicianIntervention.id),
        func.coalesce(func.sum(TechnicianIntervention.hours), 0),
        func.coalesce(func.avg(TechnicianIntervention.hours), 0),
    ).outerjoin(TechnicianIntervention, TechnicianIntervention.technician_id == Technician.id).filter(
        Technician.id == technician_id
    ).group_by(Technician.id).first()
    if not row: return None
    return {"technician_id": row[0], "full_name": row[1], "specialization": row[2],
            "interventions": int(row[3] or 0), "labor_hours": float(row[4] or 0),
            "average_hours_per_intervention": float(row[5] or 0)}


def list_repairs(db: Session, fault_id=None, workshop_type=None, status=None):
    q = db.query(Repair).options(joinedload(Repair.fault).joinedload(Fault.equipment))
    if fault_id: q = q.filter(Repair.fault_id == fault_id)
    if workshop_type: q = q.filter(Repair.workshop_type == workshop_type)
    if status: q = q.filter(Repair.status == status)
    return q.order_by(Repair.repair_date.desc(), Repair.id.desc()).all()


def change_repair_status(db: Session, repair: Repair, new_status: str):
    if new_status not in {"in_progress", "completed", "cancelled"}:
        raise ValueError("حالة الإصلاح غير صحيحة")
    repair.status = new_status
    if new_status == "completed":
        repair.fault.status = "repaired"
    elif new_status == "in_progress" and repair.fault.status in {"repaired", "closed"}:
        repair.fault.status = "repairing"
    _sync_equipment_from_faults(db, repair.fault.equipment_id)
    db.commit()
    db.refresh(repair)
    return repair


def technician_detail_analysis(db: Session, technician_id: int):
    technician = db.query(Technician).filter(Technician.id == technician_id).first()
    if not technician:
        return None
    base = db.query(TechnicianIntervention).filter(
        TechnicianIntervention.technician_id == technician_id
    )
    total_interventions = base.count()
    total_hours = db.query(func.coalesce(func.sum(TechnicianIntervention.hours), 0)).filter(
        TechnicianIntervention.technician_id == technician_id
    ).scalar()
    equipment_count = db.query(func.count(func.distinct(Fault.equipment_id))).join(
        Repair, Repair.id == TechnicianIntervention.repair_id
    ).join(Fault, Fault.id == Repair.fault_id).filter(
        TechnicianIntervention.technician_id == technician_id
    ).scalar()
    completed_repairs = db.query(func.count(func.distinct(Repair.id))).join(
        TechnicianIntervention, TechnicianIntervention.repair_id == Repair.id
    ).filter(
        TechnicianIntervention.technician_id == technician_id,
        Repair.status == "completed",
    ).scalar()
    fault_types = db.query(
        Fault.fault_type, func.count(func.distinct(Fault.id))
    ).join(Repair, Repair.fault_id == Fault.id).join(
        TechnicianIntervention, TechnicianIntervention.repair_id == Repair.id
    ).filter(
        TechnicianIntervention.technician_id == technician_id
    ).group_by(Fault.fault_type).order_by(
        func.count(func.distinct(Fault.id)).desc()
    ).all()
    return {
        "technician_id": technician.id,
        "full_name": technician.full_name,
        "specialization": technician.specialization,
        "interventions": int(total_interventions),
        "labor_hours": float(total_hours or 0),
        "average_hours_per_intervention": float(total_hours or 0) / total_interventions if total_interventions else 0,
        "equipment_count": int(equipment_count or 0),
        "completed_repairs": int(completed_repairs or 0),
        "fault_types": [{"type": t or "غير محدد", "count": int(n)} for t,n in fault_types],
    }
