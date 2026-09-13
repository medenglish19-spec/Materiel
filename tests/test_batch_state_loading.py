from datetime import date
import inspect


def test_battery_batch_state_helper_is_available():
    from app.modules.batteries.services import current_states

    assert callable(current_states)


def test_tire_batch_state_helper_is_available():
    from app.modules.tires.batch_state import current_states

    assert callable(current_states)


def test_tire_history_latest_installation_wins_by_date_then_id():
    from app.modules.tires.services import _state_from_history
    from app.modules.tires.models import TireMovement

    movements = [
        TireMovement(id=4, tire_id=1, movement_date=date(2026, 2, 1), movement_type="install", equipment_id=20, position_id=2),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 1), movement_type="remove", equipment_id=None, position_id=None),
        TireMovement(id=1, tire_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10, position_id=1),
    ]

    state = _state_from_history(movements)

    assert state["installed"] is True
    assert state["equipment_id"] == 20
    assert state["position_id"] == 2


def test_tire_remove_reason_distinguishes_damaged_expired_and_stock():
    from app.modules.tires.services import _remove_disposition
    from app.modules.tires.models import TireMovement

    damaged = TireMovement(reason="تالف")
    expired = TireMovement(reason="انتهاء الصلاحية")
    stock = TireMovement(reason="إعادة إلى المخزون")

    assert _remove_disposition(damaged) == "damaged"
    assert _remove_disposition(expired) == "expired"
    assert _remove_disposition(stock) == "stock"


def test_tire_history_remove_then_install_returns_to_installed():
    from app.modules.tires.services import _state_from_history
    from app.modules.tires.models import TireMovement

    movements = [
        TireMovement(id=1, tire_id=1, movement_date=date(2025, 1, 1), movement_type="install", equipment_id=10, position_id=1),
        TireMovement(id=2, tire_id=1, movement_date=date(2026, 1, 1), movement_type="remove", equipment_id=None, position_id=None, reason="إصلاح"),
        TireMovement(id=3, tire_id=1, movement_date=date(2026, 2, 1), movement_type="install", equipment_id=20, position_id=3),
    ]

    state = _state_from_history(movements)

    assert state["installed"] is True
    assert state["equipment_id"] == 20
    assert state["position_id"] == 3
    assert state["disposition"] == "installed"


def test_tire_list_page_uses_one_batch_snapshot_and_no_single_state_lookup():
    from app.modules.tires import router

    source = inspect.getsource(router.tires_page)

    assert source.count("batch_state.current_states(db)") == 1
    assert "batch_state.dashboard_stats(db)" not in source
    assert "services.current_state(" not in source


def test_tire_equipment_page_reuses_one_batch_snapshot_for_rows_and_positions():
    from app.modules.tires import router

    source = inspect.getsource(router.equipment_tires_page)

    assert source.count("batch_state.current_states(db)") == 1
    assert "batch_state._installed_for_equipment_from_snapshot" in source
    assert "batch_state.equipment_position_view_from_snapshot" in source
    assert "batch_state.installed_for_equipment(db, equipment_id)" not in source
    assert "batch_state.equipment_position_view(db, equipment_id)" not in source


def test_tire_detail_keeps_single_state_compatibility_path():
    from app.modules.tires import router, services

    assert callable(services.current_state)
    assert "services.current_state(db, tire_id)" in inspect.getsource(router.tire_detail)


def test_tire_dashboard_uses_batch_state_and_only_expired_installed_tires():
    from app.modules.dashboard import router

    source = inspect.getsource(router.dashboard_page)

    assert "tire_batch_state.current_states(db)" in source
    assert "state.get(\"installed\")" in source
    assert "tire_services.tire_condition(tire, state) == \"expired\"" in source
    assert "tire_services.current_state" not in source


def test_tire_batch_snapshot_stats_match_expected_statuses():
    from types import SimpleNamespace
    from app.modules.tires.batch_state import dashboard_stats_from_snapshot

    tires = [
        SimpleNamespace(id=1, expiry_date=date(2030, 1, 1)),
        SimpleNamespace(id=2, expiry_date=date(2020, 1, 1)),
        SimpleNamespace(id=3, expiry_date=date(2030, 1, 1)),
        SimpleNamespace(id=4, expiry_date=date(2030, 1, 1)),
    ]
    states = {
        1: {"installed": True, "disposition": "installed"},
        2: {"installed": True, "disposition": "installed"},
        3: {"installed": False, "disposition": "stock"},
        4: {"installed": False, "disposition": "disposed"},
    }

    counts = dashboard_stats_from_snapshot(tires, states)

    assert counts["total"] == 4
    assert counts["installed"] == 1
    assert counts["expired"] == 1
    assert counts["stock"] == 1
    assert counts["disposed"] == 1


def test_tire_remove_ui_bypasses_model_configuration_requirements():
    from pathlib import Path

    template = Path("app/modules/tires/templates/tire_detail.html").read_text(encoding="utf-8")

    assert "movementSubmit.disabled=movement.value!=='remove'" in template
    assert "equipment.disabled=remove" in template
    assert "position.disabled=remove" in template
    assert "movementSubmit.disabled=false" in template


def test_tire_expiry_is_date_based_and_not_expired_on_exact_expiry_date():
    from types import SimpleNamespace
    from app.modules.tires.services import tire_condition

    tire = SimpleNamespace(expiry_date=date(2026, 9, 13))

    assert tire_condition(tire, {"installed": True, "disposition": "installed"}, today=date(2026, 9, 12)) == "good"
    assert tire_condition(tire, {"installed": True, "disposition": "installed"}, today=date(2026, 9, 13)) == "good"
    assert tire_condition(tire, {"installed": True, "disposition": "installed"}, today=date(2026, 9, 14)) == "expired"


def test_all_tire_templates_are_arabic_rtl():
    from pathlib import Path

    template_dir = Path("app/modules/tires/templates")
    templates = sorted(template_dir.glob("*.html"))

    assert templates
    for template in templates:
        content = template.read_text(encoding="utf-8")
        assert '<html lang="ar" dir="rtl">' in content, template.name


def test_equipment_detail_exposes_current_installed_tire_table_data():
    from pathlib import Path
    from app.modules.equipment import router

    source = inspect.getsource(router.equipment_detail_page)
    template = Path("app/modules/equipment/templates/equipment_detail.html").read_text(encoding="utf-8")

    assert "tire_services.installed_for_equipment(db,equipment_id)" in source or "tire_services.installed_for_equipment(db, equipment_id)" in source
    assert "installed_tires" in template
    assert "هذه هي الإطارات المركبة حاليًا حسب آخر حركة صحيحة لكل إطار" in template


def test_battery_history_ordering_remains_date_then_id():
    from app.modules.batteries.services import _state_from_history
    from app.modules.batteries.models import BatteryMovement

    movements = [
        BatteryMovement(id=2, battery_id=1, movement_date=date(2026, 1, 1), movement_type="remove"),
        BatteryMovement(id=1, battery_id=1, movement_date=date(2026, 1, 1), movement_type="install", equipment_id=10),
        BatteryMovement(id=3, battery_id=1, movement_date=date(2026, 2, 1), movement_type="install", equipment_id=20),
    ]

    state = _state_from_history(movements)

    assert state["installed"] is True
    assert state["equipment_id"] == 20


def test_battery_exact_due_date_is_replacement_threshold():
    from app.modules.batteries.services import _add_years

    first_service = date(2021, 5, 17)
    due = _add_years(first_service, 6)

    assert due == date(2027, 5, 17)
    assert date(2027, 5, 16) < due
    assert date(2027, 5, 17) >= due
