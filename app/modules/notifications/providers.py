"""
modules/notifications/providers.py
-----------------------------------
مزوّدو الإشعارات: كل وحدة تقدّم ما تملكه من بيانات، والموحّد
(`app/modules/notifications/services.py`) يدمجها ويرتّبها حسب الخطورة.

قواعد المعمارية:
- مصدر البيانات يبقى داخل الوحدة المالكة له؛ المزوّد يستدعي خدماتها ولا
  يعيد صياغة قواعده.
- كل مزوّد يوقّع نفسه عند استيراد الحزمة (انظر `notifications/__init__.py`).
- لا استعلامات N+1 جديدة: الإطارات والبطاريات تُحمَّل دفعة واحدة.
"""

from datetime import date

from sqlalchemy.orm import joinedload

from app.modules.batteries import services as battery_services
from app.modules.equipment.models import Equipment
from app.modules.maintenance.services import (
    current_meter_value,
    effective_operations_for_equipment,
    latest_readings,
    latest_records,
    measurement_unit,
    status_for,
)
from app.modules.notifications.services import register_provider
from app.modules.tires import batch_state as tire_batch_state
from app.modules.tires import services as tire_services

__all__ = [
    "maintenance_due_provider",
    "expired_tire_provider",
    "battery_replacement_provider",
]


def _equipment_label(equipment) -> str:
    return (
        equipment.registration_number
        or equipment.asset_code
        or f"عتاد #{equipment.id}"
    )


def _remaining_hint(equipment, remaining, meta) -> str:
    unit = measurement_unit(equipment)
    if remaining is not None and unit in {"km", "hours"}:
        suffix = "كم" if unit == "km" else "ساعة"
        return f"متبقي {int(remaining)} {suffix}"
    days = meta.get("remaining_days") if meta else None
    if days is not None:
        return f"متبقي {days} يوم"
    return "يحتاج قراءة عداد أو تاريخ سجل"


def maintenance_due_provider(db) -> list[dict]:
    """العمليات المستحقة أو المتقاربة على العتاد (خدمات الصيانة هي الحاكمة)."""
    equipment = (
        db.query(Equipment)
        .options(
            joinedload(Equipment.equipment_type),
            joinedload(Equipment.equipment_model),
        )
        .order_by(Equipment.registration_number, Equipment.asset_code)
        .all()
    )
    readings = latest_readings(db)
    records = latest_records(db)

    # العمليات تعتمد على طراز العتاد فقط، فالاستعلام مرة واحدة لكل طراز
    # (وإلا تكرر استعلام لكل عتاد على اللوحة).
    operations_by_model: dict = {}
    notes: list[dict] = []
    for eq in equipment:
        # بلا نوع عتاد لا يمكن تحديد وحدة القياس (كم/ساعة) => لا حساب استحقاق.
        if eq.equipment_type is None:
            continue
        model_id = eq.equipment_model_id
        if model_id not in operations_by_model:
            operations_by_model[model_id] = effective_operations_for_equipment(db, eq)
        current_value = current_meter_value(eq, readings.get(eq.id))
        for operation in operations_by_model[model_id]:
            record = records.get((eq.id, operation.id))
            state, css, remaining, meta = status_for(
                operation, eq, record, current_value
            )
            if css not in {"danger", "warning"}:
                continue
            notes.append(
                {
                    "key": f"maintenance:{eq.id}:{operation.id}",
                    "severity": "overdue" if css == "danger" else "upcoming",
                    "module": "maintenance",
                    "title": f"{operation.name} — {_equipment_label(eq)}",
                    "detail": f"{state} · {_remaining_hint(eq, remaining, meta)}",
                    "url": "/maintenance/periodic",
                }
            )
    return notes


def expired_tire_provider(db) -> list[dict]:
    """الإطارات المركبة المنتهية فقط (نفس قاعدة لوحة التحكم)."""
    tires, states = tire_batch_state.current_states(db)
    notes: list[dict] = []
    for tire in tires:
        state = states.get(tire.id)
        if not state or not state.get("installed"):
            continue
        if tire_services.tire_condition(tire, state) != "expired":
            continue
        equipment = state.get("equipment")
        position = state.get("position")
        detail = " · ".join(
            part
            for part in (
                _equipment_label(equipment) if equipment else None,
                position.name if position else None,
            )
            if part
        )
        notes.append(
            {
                "key": f"tire:{tire.id}",
                "severity": "overdue",
                "module": "tires",
                "title": f"إطار مستحق للاستبدال: {tire.serial_number}",
                "detail": detail or "غير مرتبط بعتاد مركب",
                "url": f"/tires/{tire.id}",
            }
        )
    return notes


def battery_replacement_provider(db) -> list[dict]:
    """البطاريات المركبة التي بلغت موعد الاستبدال (تنبيه وقائي)."""
    batteries, states = battery_services.current_states(db)
    today = date.today()
    notes: list[dict] = []
    for battery in batteries:
        state = states.get(battery.id)
        if not state or not state.get("installed"):
            continue
        equipment = state.get("equipment")
        due_date = battery_services.replacement_due_date(db, battery, equipment)
        if due_date is None or today < due_date:
            continue
        notes.append(
            {
                "key": f"battery:{battery.id}",
                "severity": "overdue",
                "module": "batteries",
                "title": f"بطارية مستحقة الاستبدال: {battery.serial_number}",
                "detail": f"{_equipment_label(equipment)} · موعد الاستبدال {due_date}",
                "url": f"/batteries/{battery.id}",
            }
        )
    return notes


# التسجيل الذاتي عند استيراد الحزمة.
register_provider(maintenance_due_provider)
register_provider(expired_tire_provider)
register_provider(battery_replacement_provider)
