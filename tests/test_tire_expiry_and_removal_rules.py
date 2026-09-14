from datetime import date, datetime
from types import SimpleNamespace

from app.modules.tires import services
from app.modules.tires.models import Tire


def test_manual_expiry_field_has_false_default():
    column = Tire.__table__.c.expiry_date_manual
    assert column.default is not None
    assert column.default.arg is False


def test_explicit_removal_disposition_has_priority_over_free_text_reason():
    movement = SimpleNamespace(removal_disposition="expired", reason="إطار سليم للمخزون")
    assert services._remove_disposition(movement) == "expired"


def test_legacy_removal_reason_is_still_supported():
    movement = SimpleNamespace(removal_disposition=None, reason="تالف")
    assert services._remove_disposition(movement) == "damaged"


def test_same_day_removal_and_installation_have_distinct_order():
    remove = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 10), id=2)
    install = SimpleNamespace(movement_date=date(2026, 9, 14), movement_datetime=datetime(2026, 9, 14, 8, 25), id=1)
    assert sorted([install, remove], key=services._movement_datetime) == [remove, install]
