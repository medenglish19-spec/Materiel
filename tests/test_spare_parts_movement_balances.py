from decimal import Decimal

from app.modules.spare_parts_movements.services import _available, _status


def test_available_never_goes_above_received_balance():
    assert _available(Decimal("3"), Decimal("4"), Decimal("0")) == Decimal("0")


def test_corrupt_distribution_balance_is_not_reported_as_fully_distributed():
    assert _status(Decimal("3"), Decimal("4"), Decimal("0")) == "invalid_distribution_over_received"


def test_valid_full_distribution_stays_fully_distributed():
    assert _status(Decimal("3"), Decimal("3"), Decimal("0")) == "fully_distributed"
