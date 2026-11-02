from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.core.permissions import Role, require_role
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
def operations(
    request: Request,
    deleted_count: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
            'can_delete_audit': settings.DEV_DISABLE_AUTH or current_user.role == Role.ADMIN.value,
            'deleted_count': deleted_count,
        },
    )


@router.post('/delete-selected')
def delete_selected_changes(
    change_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    ids = list(dict.fromkeys(change_ids))
    if len(ids) > 500:
        raise HTTPException(status_code=400, detail="يمكن حذف 500 سطر كحد أقصى في المرة الواحدة.")
    rows = db.query(MeterReadingChange).filter(MeterReadingChange.id.in_(ids)).all() if ids else []
    deleted_count = len(rows)
    for row in rows:
        db.delete(row)
    if deleted_count:
        db.commit()
    return RedirectResponse(
        url=f'/meter-readings/operations?deleted={deleted_count}', status_code=303
    )


@router.post('/{change_id:int}/delete')
def delete_change(
    change_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    change = db.get(MeterReadingChange, change_id)
    if change is None:
        return RedirectResponse(url='/meter-readings/operations', status_code=303)
    db.delete(change)
    db.commit()
    return RedirectResponse(url='/meter-readings/operations?deleted=1', status_code=303)
