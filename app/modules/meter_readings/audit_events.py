from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.modules.equipment.models import Equipment
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.audit import MeterReadingOperation, MeterReadingOperationEvent

_current_actor = ContextVar('meter_audit_actor', default=None)
_current_kind = ContextVar('meter_audit_kind', default='manual')


def set_request_actor(user_id, kind='manual'):
    _current_actor.set(user_id)
    _current_kind.set(kind)


@event.listens_for(Session, 'after_flush')
def _collect_meter_readings(session, flush_context):
    ids = session.info.setdefault('_meter_audit_reading_ids', [])
    for obj in session.new:
        if isinstance(obj, MeterReading) and obj.id is not None:
            equipment = session.get(Equipment, obj.equipment_id)
            if equipment is not None:
                obj.equipment_status = str(equipment.operational_status or 'available')
            ids.append(obj.id)


@event.listens_for(Session, 'after_rollback')
def _clear_meter_audit_on_rollback(session):
    session.info.pop('_meter_audit_reading_ids', None)


@event.listens_for(Session, 'after_commit')
def _write_meter_operation(session):
    ids = list(dict.fromkeys(session.info.pop('_meter_audit_reading_ids', [])))
    if not ids:
        return
    actor = _current_actor.get()
    kind = _current_kind.get()
    try:
        from app.database.session import SessionLocal
        with SessionLocal() as audit_db:
            readings = audit_db.query(MeterReading).filter(MeterReading.id.in_(ids)).all()
            if not readings:
                return
            equipment_ids = sorted({r.equipment_id for r in readings})
            op = MeterReadingOperation(
                kind=kind,
                equipment_id=equipment_ids[0] if len(equipment_ids) == 1 else None,
                created_by_id=actor,
                status='completed',
                total_rows=len(readings),
                accepted_rows=len(readings),
                rejected_rows=0,
                reading_ids=[r.id for r in readings],
            )
            audit_db.add(op)
            audit_db.flush()
            audit_db.add(MeterReadingOperationEvent(operation_id=op.id, event_type='created', actor_id=actor, details=f'بدأت عملية {kind} وتم ربط {len(readings)} قراءة بها.'))
            audit_db.add(MeterReadingOperationEvent(operation_id=op.id, event_type='completed', actor_id=actor, details=f'تم حفظ {len(readings)} قراءة بنجاح.'))
            audit_db.commit()
    except Exception:
        # فشل سجل التدقيق لا يجب أن يلغي القراءة التي تم حفظها بالفعل.
        return
