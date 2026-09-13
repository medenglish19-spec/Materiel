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
