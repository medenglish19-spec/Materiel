from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.modules.users.models import User
from app.modules.equipment.models import Equipment
from app.modules.meter_readings.audit import MeterReadingChange

router = APIRouter(prefix='/meter-readings/operations', tags=['Meter Reading Operations'])
templates = get_module_templates('app/modules/meter_readings/templates')


def _fmt(value):
    if value is None: return '—'
    try:
        n = float(value)
        return f'{int(n):,}' if n.is_integer() else f'{n:,.1f}'
    except Exception: return str(value)


def _action(value): return {'add': 'إضافة قراءة', 'update': 'تعديل قراءة'}.get(value, value)


@router.get('', response_class=HTMLResponse)
def operations(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    changes = db.query(MeterReadingChange).order_by(MeterReadingChange.changed_at.desc(), MeterReadingChange.id.desc()).limit(500).all()
    actor_ids = [x.actor_id for x in changes if x.actor_id]
    equipment_ids = [x.equipment_id for x in changes if x.equipment_id]
    names = {u.id: f'{u.full_name} ({u.username})' for u in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}
    equipment_map = {e.id: e for e in db.query(Equipment).filter(Equipment.id.in_(equipment_ids)).all()} if equipment_ids else {}

    return templates.TemplateResponse(
        request=request,
        name='meter_reading_operations.html',
        context={
            'request': request,
            'changes': changes,
            'names': names,
            'equipment_map': equipment_map,
            'format_value': _fmt,
            'action_label': _action,
        },
    )
