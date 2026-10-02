"""الكمية في طلبات الغيار عدد صحيح: المطلوبة 1 فأكثر، والمستلمة 1 فأكثر.

الصفر حالة داخلية تعني «لم يُستلم بعد»: يُحفظ تلقائياً عند إنشاء الطلب،
لكن لا يُقبل تسجيل استلام بصفر.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.faults_repairs.schemas import RepairPartCreate
from app.modules.spare_parts_requests.schemas import (
    SparePartRequestItemCreate,
    SparePartRequestItemUpdate,
)


ROOT = Path(__file__).resolve().parents[1]
REQUEST_TEMPLATE = (
    ROOT / "app" / "modules" / "spare_parts_requests" / "templates" / "requests.html"
)


def _create(**kwargs):
    payload = {"spare_part_id": 1, "requested_quantity": 2}
    payload.update(kwargs)
    return SparePartRequestItemCreate(**payload)


class TestRequestedQuantity:
    def test_accepts_whole_numbers(self):
        assert _create(requested_quantity=1).requested_quantity == 1
        assert _create(requested_quantity=7).requested_quantity == 7

    def test_accepts_a_whole_number_sent_as_a_float(self):
        # المتصفح قد يرسل 3.0 بعد قسمة، وهي عدد صحيح فعلاً
        assert _create(requested_quantity=3.0).requested_quantity == 3

    def test_rejects_a_fractional_value(self):
        with pytest.raises(ValidationError):
            _create(requested_quantity=2.5)

    def test_rejects_a_fractional_value_sent_as_a_string(self):
        with pytest.raises(ValidationError):
            _create(requested_quantity="2.5")

    def test_rejects_zero(self):
        with pytest.raises(ValidationError):
            _create(requested_quantity=0)

    def test_rejects_a_negative_value(self):
        with pytest.raises(ValidationError):
            _create(requested_quantity=-1)


class TestReceivedQuantity:
    def test_omitting_it_means_nothing_received_yet(self):
        # إنشاء الطلب لا يرسل هذه الحقل، فيبقى صفراً كحالة داخلية.
        assert _create().received_quantity == 0

    def test_accepts_whole_numbers(self):
        assert _create(received_quantity=4).received_quantity == 4

    def test_rejects_a_fractional_value(self):
        with pytest.raises(ValidationError):
            _create(received_quantity=2.5)

    def test_rejects_zero_because_a_receipt_cannot_be_empty(self):
        with pytest.raises(ValidationError):
            _create(received_quantity=0)

    def test_rejects_a_negative_value(self):
        with pytest.raises(ValidationError):
            _create(received_quantity=-1)

    def test_stays_optional_on_update(self):
        assert SparePartRequestItemUpdate().received_quantity is None

    def test_requested_quantity_stays_optional_on_update(self):
        assert SparePartRequestItemUpdate().requested_quantity is None


class TestUpdateQuantities:
    def test_accepts_whole_numbers(self):
        item = SparePartRequestItemUpdate(requested_quantity=5, received_quantity=2)
        assert item.requested_quantity == 5
        assert item.received_quantity == 2

    def test_rejects_a_fractional_requested_quantity(self):
        with pytest.raises(ValidationError):
            SparePartRequestItemUpdate(requested_quantity=1.5)

    def test_rejects_a_fractional_received_quantity(self):
        with pytest.raises(ValidationError):
            SparePartRequestItemUpdate(received_quantity=1.5)

    def test_rejects_recording_a_receipt_of_zero(self):
        with pytest.raises(ValidationError):
            SparePartRequestItemUpdate(received_quantity=0)

    def test_rejects_a_negative_received_quantity(self):
        with pytest.raises(ValidationError):
            SparePartRequestItemUpdate(received_quantity=-1)


class TestConsumedPartQuantity:
    """الكمية المستهلكة في التصليح عدد صحيح أيضاً."""

    def _create(self, **kwargs):
        payload = {"repair_id": 1, "spare_part_id": 1, "quantity": 2,
                   "distribution_document": "وثيقة توزيع"}
        payload.update(kwargs)
        return RepairPartCreate(**payload)

    def test_accepts_whole_numbers(self):
        assert self._create(quantity=3).quantity == 3

    def test_rejects_a_fractional_value(self):
        with pytest.raises(ValidationError):
            self._create(quantity=1.5)

    def test_rejects_zero(self):
        with pytest.raises(ValidationError):
            self._create(quantity=0)

    def test_rejects_a_negative_value(self):
        with pytest.raises(ValidationError):
            self._create(quantity=-2)


class TestFormInputsAreWholeNumbers:
    """المتصفح يجب أن يرفض الكسر قبل أن يصل إلى الخادم."""

    def setup_method(self):
        self.html = REQUEST_TEMPLATE.read_text(encoding="utf-8")

    def test_requested_quantity_step_is_one(self):
        assert 'class="new-qty" type="number" min="1" step="1"' in self.html

    def test_received_quantity_step_is_one(self):
        assert 'class="received" type="number" min="1" step="1"' in self.html

    def test_no_quantity_input_still_accepts_two_decimals(self):
        assert 'step="0.01"' not in self.html


class TestConsumedPartInputIsWholeNumber:
    def setup_method(self):
        self.html = (
            ROOT / "app" / "modules" / "faults_repairs" / "templates" / "repair_detail.html"
        ).read_text(encoding="utf-8")

    def test_quantity_step_is_one(self):
        assert 'name="quantity" min="1" step="1"' in self.html