from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.modules.tires import services
from app.modules.tires.models import TireMovement


def test_movement_datetime_is_the_authoritative_ordering_value():
    early = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 15), id=20)
    late = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 30), id=1)
    assert services._movement_datetime(early) < services._movement_datetime(late)


def test_legacy_date_only_movement_remains_backward_compatible():
    legacy = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=None, id=1)
    assert services._movement_datetime(legacy) == datetime(2026, 9, 14, 0, 0)


def test_same_timestamp_for_same_tire_is_rejected_but_same_day_different_times_are_allowed():
    existing = [SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 15), id=1)]
    services._validate_same_timestamp(existing, datetime(2026, 9, 14, 8, 30))
    with pytest.raises(ValueError, match="نفس التاريخ والوقت"):
        services._validate_same_timestamp(existing, datetime(2026, 9, 14, 8, 15))


def test_tire_movement_model_has_precise_datetime_column():
    assert "movement_datetime" in TireMovement.__table__.columns
    assert TireMovement.__table__.c.movement_datetime.nullable is True
