"""M2 — ربط وحدة الإشعارات باللوحة: مزوّدون مسجّلون + دمج بالخطورة + عقد القالب."""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل أي استعلام)
from app.modules.maintenance.services import CONDITION_MODEL, ModelCondition, CONDITION_UNSET
from app.modules.notifications import providers, services

TEMPLATE = Path("app/modules/dashboard/templates/dashboard.html")


def _model_condition(equipment_model_id, **condition):
    """شرط طراز حقيقي كما يقرأه محرك الاستحقاق من علاقة العملية بالطراز.
    
    Warning settings are unified at the operation level, not per-model.
    """
    # Filter out warning fields - they belong on the operation, not the model condition
    condition = {k: v for k, v in condition.items() if k not in ("warning_km", "warning_days")}
    values = {"condition_source": CONDITION_MODEL, "equipment_model_id": equipment_model_id}
    values.update(condition)
    return ModelCondition(**values)


def _use_model_condition(monkeypatch, **condition):
    """استبدال قراءة شرط الطراز بشرط حقيقي بدل الوصول إلى القاعدة."""
    monkeypatch.setattr(
        providers,
        "condition_for_equipment",
        lambda db, operation, equipment: _model_condition(equipment.equipment_model_id, **condition),
    )


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def options(self, *args, **kwargs):  # noqa: D102
        return self

    def order_by(self, *args, **kwargs):  # noqa: D102
        return self

    def all(self):  # noqa: D102
        return list(self._rows)


class _DB:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def query(self, *args, **kwargs):  # noqa: D102
        return _Query(self._rows)


def _equipment(**overrides):
    values = {
        "id": 5,
        "registration_number": "EQ-5",
        "asset_code": None,
        "equipment_type": SimpleNamespace(measurement_unit="km"),
        "equipment_model": None,
        "equipment_model_id": 11,
        "current_odometer": Decimal("0"),
        "current_hours": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _operation(**overrides):
    values = {
        "id": 3,
        "name": "تغيير الزيت",
        "interval_km": 10000,
        "interval_hours": None,
        "interval_days": None,
        "warning_km": None,
        "warning_days": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------- التسجيل والدمج


def test_importing_the_package_registers_the_three_providers():
    registered = {fn.__name__ for fn in services._PROVIDERS}
    assert {
        "maintenance_due_provider",
        "expired_tire_provider",
        "battery_replacement_provider",
    } <= registered


def test_get_all_notifications_merges_by_key_and_sorts_by_severity(monkeypatch):
    def overdue_provider(db):
        return [{"key": "a", "severity": "overdue"}]

    def upcoming_provider(db):
        return [{"key": "a", "severity": "upcoming"}, {"key": "b", "severity": "upcoming"}]

    monkeypatch.setattr(services, "_PROVIDERS", [overdue_provider, upcoming_provider])

    merged = services.get_all_notifications(_DB())

    assert [note["key"] for note in merged] == ["a", "b"], "المستحقة أولًا"
    assert merged[0]["severity"] == "overdue", "الخطورة الأعلى تفوز عند تكرار المفتاح"


# ---------------------------------------------------------------- مزوّد الصيانة


def test_maintenance_provider_reports_overdue_operations(monkeypatch):
    record = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {(5, 3): record})
    monkeypatch.setattr(
        providers, "effective_operations_for_equipment", lambda db, eq, **kwargs: [_operation()]
    )
    _use_model_condition(monkeypatch, interval_km=10000)

    notes = providers.maintenance_due_provider(
        _DB([_equipment(current_odometer=Decimal("20000"))])
    )

    assert len(notes) == 1
    note = notes[0]
    assert note["key"] == "maintenance:5:3"
    assert note["severity"] == "overdue"
    assert note["module"] == "maintenance"
    assert note["url"] == "/maintenance/periodic"
    assert "تغيير الزيت" in note["title"] and "EQ-5" in note["title"]
    assert "مستحقة الآن" in note["detail"]


def test_maintenance_provider_reports_upcoming_inside_warning_window(monkeypatch):
    record = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {(5, 3): record})
    monkeypatch.setattr(
        providers,
        "effective_operations_for_equipment",
        lambda db, eq, **kwargs: [_operation(interval_km=20000, warning_km=Decimal("1000"))],
    )
    _use_model_condition(monkeypatch, interval_km=20000)

    notes = providers.maintenance_due_provider(
        _DB([_equipment(current_odometer=Decimal("19500"))])
    )

    assert [note["severity"] for note in notes] == ["upcoming"]
    assert "تقترب" in notes[0]["detail"]


def test_maintenance_provider_stays_silent_within_schedule(monkeypatch):
    record = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {(5, 3): record})
    monkeypatch.setattr(
        providers,
        "effective_operations_for_equipment",
        lambda db, eq, **kwargs: [_operation(interval_km=10000, warning_km=Decimal("100"))],
    )
    _use_model_condition(monkeypatch, interval_km=20000)

    assert providers.maintenance_due_provider(_DB([_equipment()])) == []


def test_maintenance_provider_does_not_invent_a_condition_for_an_unset_model(monkeypatch):
    """بلا شرط محفوظ للطراز لا يُبنى إنذار من القيمة القديمة على العملية."""
    record = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {(5, 3): record})
    monkeypatch.setattr(
        providers,
        "effective_operations_for_equipment",
        # العملية تحمل قيمة قديمة مشتركة، والطراز بلا شرط محفوظ.
        lambda db, eq, **kwargs: [_operation(interval_km=10000, warning_km=Decimal("900"))],
    )
    _use_model_condition(monkeypatch, condition_source=CONDITION_UNSET)

    assert providers.maintenance_due_provider(
        _DB([_equipment(current_odometer=Decimal("999999"))])
    ) == []


def test_maintenance_provider_queries_operations_once_per_model(monkeypatch):
    """منع N+1: العمليات تعتمد على الطراز فقط، فالاستعلام مرة واحدة لكل طراز."""
    record = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    calls: list = []

    def _operations(db, eq, **kwargs):
        calls.append(eq.equipment_model_id)
        return [_operation()]

    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {(5, 3): record, (6, 3): record})
    def _operations_with_warning(db, eq, **kwargs):
        calls.append(eq.equipment_model_id)
        return [_operation(warning_km=Decimal("1000"))]
    monkeypatch.setattr(providers, "effective_operations_for_equipment", _operations_with_warning)
    _use_model_condition(monkeypatch, interval_km=20000)

    notes = providers.maintenance_due_provider(
        _DB(
            [
                _equipment(id=5, registration_number="EQ-5", current_odometer=Decimal("19500")),
                _equipment(id=6, registration_number="EQ-6", current_odometer=Decimal("19500")),
            ]
        )
    )

    assert calls == [11], "طراز واحد => استعلام واحد لعتدين"
    assert len(notes) == 2


def test_maintenance_provider_uses_each_equipment_own_model_condition(monkeypatch):
    """الشرط يُقرأ لطراز كل عتاد؛ عتادان بطرازين مختلفين يحصلان على شرطين مختلفين."""
    record_5 = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    record_6 = SimpleNamespace(meter_value=Decimal("0"), maintenance_date=date(2026, 1, 1))
    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {(5, 3): record_5, (6, 3): record_6})
    monkeypatch.setattr(
        providers, "effective_operations_for_equipment", lambda db, eq, **kwargs: [_operation(warning_km=Decimal("1000"))]
    )
    conditions = {
        11: _model_condition(11, interval_km=Decimal("20000")),
        12: _model_condition(12, interval_km=Decimal("100")),
    }
    seen: list = []

    def _condition(db, operation, equipment):
        seen.append(equipment.equipment_model_id)
        return conditions[equipment.equipment_model_id]

    monkeypatch.setattr(providers, "condition_for_equipment", _condition)

    notes = providers.maintenance_due_provider(
        _DB(
            [
                _equipment(id=5, registration_number="EQ-5", current_odometer=Decimal("19500")),
                _equipment(id=6, registration_number="EQ-6", equipment_model_id=12, current_odometer=Decimal("100050")),
            ]
        )
    )

    assert seen == [11, 12], "شرط كل عتاد يُقرأ من طرازه"
    # الطراز 11 على بعد 500 كم، والطراز 12 تجاوز فاصله البالغ 100 كم.
    assert {(note["key"], note["severity"]) for note in notes} == {
        ("maintenance:5:3", "upcoming"),
        ("maintenance:6:3", "overdue"),
    }


def test_maintenance_provider_skips_equipment_without_type(monkeypatch):
    monkeypatch.setattr(providers, "latest_readings", lambda db: {})
    monkeypatch.setattr(providers, "latest_records", lambda db: {})
    monkeypatch.setattr(providers, "effective_operations_for_equipment", lambda db, eq, **kwargs: [])

    assert providers.maintenance_due_provider(
        _DB([_equipment(equipment_type=None)])
    ) == []


# ---------------------------------------------------------------- مزوّد الإطارات


def test_expired_tire_provider_only_reports_installed_expired_tires(monkeypatch):
    installed = SimpleNamespace(id=7, serial_number="T-7", expiry_date=date(2020, 1, 1))
    in_stock = SimpleNamespace(id=8, serial_number="T-8", expiry_date=date(2020, 1, 1))
    states = {
        7: {
            "installed": True,
            "equipment": SimpleNamespace(registration_number="EQ-9", asset_code=None, id=9),
            "position": SimpleNamespace(name="محور أمامي"),
        },
        8: {"installed": False, "equipment": None, "position": None},
    }
    monkeypatch.setattr(
        providers.tire_batch_state,
        "current_states",
        lambda db: ([installed, in_stock], states),
    )

    notes = providers.expired_tire_provider(_DB())

    assert [note["key"] for note in notes] == ["tire:7"], "المخزون غير مركب لا يُبلَّغ عنه"
    note = notes[0]
    assert note["severity"] == "overdue"
    assert note["url"] == "/tires/7"
    assert "T-7" in note["title"]
    assert "EQ-9" in note["detail"] and "محور أمامي" in note["detail"]


def test_expired_tire_provider_ignores_healthy_tires(monkeypatch):
    healthy = SimpleNamespace(id=7, serial_number="T-7", expiry_date=date(2099, 1, 1))
    states = {7: {"installed": True, "equipment": None, "position": None}}
    monkeypatch.setattr(
        providers.tire_batch_state, "current_states", lambda db: ([healthy], states)
    )

    assert providers.expired_tire_provider(_DB()) == []


# ---------------------------------------------------------------- مزوّد البطاريات


def test_battery_provider_reports_only_installed_due_batteries(monkeypatch):
    due = SimpleNamespace(id=4, serial_number="B-4")
    in_stock = SimpleNamespace(id=5, serial_number="B-5")
    equipment = SimpleNamespace(registration_number="EQ-9", asset_code=None, id=9)
    states = {
        4: {"installed": True, "equipment": equipment},
        5: {"installed": False, "equipment": None},
    }
    monkeypatch.setattr(
        providers.battery_services, "current_states", lambda db: ([due, in_stock], states)
    )
    monkeypatch.setattr(
        providers.battery_services, "replacement_due_date", lambda db, b, e: date(2020, 1, 1)
    )

    notes = providers.battery_replacement_provider(_DB())

    assert [note["key"] for note in notes] == ["battery:4"]
    assert notes[0]["severity"] == "overdue"
    assert notes[0]["url"] == "/batteries/4"


def test_battery_provider_ignores_future_due_date(monkeypatch):
    battery = SimpleNamespace(id=4, serial_number="B-4")
    states = {4: {"installed": True, "equipment": None}}
    monkeypatch.setattr(
        providers.battery_services, "current_states", lambda db: ([battery], states)
    )
    monkeypatch.setattr(
        providers.battery_services,
        "replacement_due_date",
        lambda db, b, e: date(2099, 1, 1),
    )

    assert providers.battery_replacement_provider(_DB()) == []


# ---------------------------------------------------------------- عقد الاستهلاك


def test_dashboard_page_aggregates_and_passes_notifications():
    from app.modules.dashboard import router

    source = inspect.getsource(router.dashboard_page)

    assert "get_all_notifications(db)" in source
    assert '"notifications": notifications' in source


def test_dashboard_template_renders_the_merged_notifications_panel():
    template = TEMPLATE.read_text(encoding="utf-8")

    assert "التنبيهات الموحّدة" in template
    assert "{% for note in notifications %}" in template
    assert 'class="notif-item notif-{{ note.severity }}"' in template