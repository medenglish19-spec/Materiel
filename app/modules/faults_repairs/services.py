from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.equipment.models import Equipment
from app.modules.maintenance.models import MaintenanceRecord
from .models import Fault, Repair, SparePart, RepairPart
from .schemas import FaultCreate, FaultUpdate, RepairCreate, SparePartCreate, SparePartUpdate, RepairPartCreate


FAULT_TRANSITIONS = {
    "open": {"diagnosing", "repairing", "closed"},
    "diagnosing": {"repairing", "waiting_parts", "repaired", "closed"},
    "repairing": {"waiting_parts", "repaired"},
    "waiting_parts": {"repairing", "repaired"},
    "repaired": {"closed", "repairing"},
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
    obj = Fault(**data.model_dump(), status="open", created_by_id=user_id)
    db.add(obj); db.commit(); db.refresh(obj); return obj


def update_fault(db: Session, obj: Fault, data: FaultUpdate):
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(obj, k, v)
    if obj.reported_date > date.today(): raise ValueError("لا يمكن تسجيل عطل بتاريخ مستقبلي")
    db.commit(); db.refresh(obj); return obj


def change_fault_status(db: Session, obj: Fault, new_status: str):
    allowed = FAULT_TRANSITIONS.get(obj.status, set())
    if new_status == obj.status: return obj
    if new_status not in allowed: raise ValueError(f"لا يمكن نقل حالة العطل من {obj.status} إلى {new_status}")
    obj.status = new_status
    db.commit(); db.refresh(obj); return obj


def create_repair(db: Session, data: RepairCreate, user_id=None):
    fault = db.query(Fault).filter(Fault.id == data.fault_id).first()
    if not fault: raise ValueError("العطل غير موجود")
    if data.repair_date > date.today(): raise ValueError("لا يمكن تسجيل إصلاح بتاريخ مستقبلي")
    if data.workshop_type == "external" and not data.external_dispatch_document:
        raise ValueError("وثيقة إرسال العتاد للورشة الخارجية إلزامية")
    obj = Repair(**data.model_dump(), created_by_id=user_id)
    db.add(obj); db.commit(); db.refresh(obj); return obj


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
    hours = db.query(func.coalesce(func.sum(Repair.labor_hours), 0)).scalar()
    parts = db.query(func.coalesce(func.sum(RepairPart.quantity), 0)).scalar()
    return {"faults_total": total, "faults_by_status": by_status, "faults_by_severity": by_severity,
            "repairs_total": repairs, "labor_hours": hours, "parts_consumed": parts}


def technician_stats(db: Session):
    rows = db.query(Repair.technician, func.count(Repair.id), func.coalesce(func.sum(Repair.labor_hours),0)).group_by(Repair.technician).order_by(func.count(Repair.id).desc()).all()
    return [{"technician": n or "غير محدد", "repairs": int(c), "labor_hours": float(h or 0)} for n,c,h in rows]


def part_usage_stats(db: Session):
    rows = db.query(SparePart.part_number, SparePart.name, func.sum(RepairPart.quantity)).join(RepairPart, RepairPart.spare_part_id == SparePart.id).group_by(SparePart.id).order_by(func.sum(RepairPart.quantity).desc()).all()
    return [{"part_number": n, "name": name, "quantity": float(q or 0)} for n,name,q in rows]


def equipment_fault_stats(db: Session):
    rows = db.query(Equipment.id, Equipment.asset_code, Equipment.registration_number, func.count(Fault.id)).join(Fault, Fault.equipment_id == Equipment.id).group_by(Equipment.id).order_by(func.count(Fault.id).desc()).all()
    return [{"equipment_id": i, "asset_code": a, "registration_number": r, "faults": int(c)} for i,a,r,c in rows]
