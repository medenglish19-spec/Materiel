from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.modules.tires import services, state_engine
from app.modules.tires.models import TireMovement


def test_movement_datetime_is_the_authoritative_ordering_value():
    early = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 15), id=20)
    late = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 30), id=1)
    assert services._movement_datetime(early) < services._movement_datetime(late)


def test_movement_datetime_is_required_for_movement_records():
    missing = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=None, id=1)
    with pytest.raises(ValueError, match="وقت حركة الإطار مطلوب"):
        services._movement_datetime(missing)


def test_same_timestamp_for_same_tire_is_rejected_but_same_day_different_times_are_allowed():
    existing = [SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 15), id=1)]
    services._validate_same_timestamp(existing, datetime(2026, 9, 14, 8, 30))
    with pytest.raises(ValueError, match="نفس التاريخ والوقت"):
        services._validate_same_timestamp(existing, datetime(2026, 9, 14, 8, 15))


def test_tire_movement_model_requires_precise_datetime_and_has_database_uniqueness():
    column = TireMovement.__table__.c.movement_datetime
    assert "movement_datetime" in TireMovement.__table__.columns
    assert column.nullable is False
    constraints = {constraint.name for constraint in TireMovement.__table__.constraints}
    assert "uq_tire_movement_timestamp" in constraints
    constraint = next(c for c in TireMovement.__table__.constraints if c.name == "uq_tire_movement_timestamp")
    assert [column.name for column in constraint.columns] == ["tire_id", "movement_datetime"]


def test_state_engine_is_the_single_chronological_state_calculator():
    remove = SimpleNamespace(movement_type="remove", movement_datetime=datetime(2026, 9, 14, 8, 10), equipment_id=None, position_id=None, equipment=None, position=None, removal_disposition="stock", reason=None)
    install = SimpleNamespace(movement_type="install", movement_datetime=datetime(2026, 9, 14, 8, 25), equipment_id=10, position_id=20, equipment="equipment", position="position", removal_disposition=None, reason=None)
    state = state_engine.state_from_history([install, remove])
    assert state["installed"] is True
    assert state["equipment_id"] == 10
    assert state["position_id"] == 20
    assert state["movement"] is install


def test_same_day_removal_and_installation_have_distinct_order():
    remove = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 10), id=2)
    install = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 25), id=1)
    assert sorted([install, remove], key=services._movement_datetime) == [remove, install]
