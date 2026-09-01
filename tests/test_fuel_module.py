from decimal import Decimal

from app.modules.fuel.models import FuelRecord
from app.modules.fuel.services import ABNORMAL_FACTOR


def test_fuel_model_and_abnormal_threshold():
    assert FuelRecord.__tablename__ == "fuel_records"
    assert ABNORMAL_FACTOR == Decimal("1.20")
