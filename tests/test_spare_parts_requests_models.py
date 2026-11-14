import pytest
from sqlalchemy import CheckConstraint

from app.modules.spare_parts_requests.models import SparePartRequest, SparePartRequestItem
from app.modules.spare_parts_requests.schemas import SparePartRequestCreate
from pydantic import ValidationError


def test_spare_part_request_model_contract():
    assert SparePartRequest.__tablename__ == "spare_part_requests"
    assert SparePartRequestItem.__tablename__ == "spare_part_request_items"

    for name in (
        "source_type",
        "fault_id",
        "repair_id",
        "equipment_id",
        "status",
    ):
        assert name in SparePartRequest.__table__.columns

    for name in (
        "request_id",
        "spare_part_id",
        "requested_quantity",
        "received_quantity",
        "recipient",
        "supplier_institution",
    ):
        assert name in SparePartRequestItem.__table__.columns


def test_spare_part_request_source_and_status_constraints():
    checks = {
        c.name: str(c.sqltext)
        for c in SparePartRequest.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name
    }

    assert "ck_spare_part_request_source_type" in checks
    assert "fault" in checks["ck_spare_part_request_source_type"]
    assert "repair" in checks["ck_spare_part_request_source_type"]
    assert "need" in checks["ck_spare_part_request_source_type"]
    assert "need" in checks["ck_spare_part_request_source_match"]
    assert "ck_spare_part_request_status" in checks
    assert "pending" in checks["ck_spare_part_request_status"]
    assert "approved" in checks["ck_spare_part_request_status"]
    assert "rejected" in checks["ck_spare_part_request_status"]
    assert "cancelled" in checks["ck_spare_part_request_status"]


def test_general_need_request_does_not_accept_an_association():
    request = SparePartRequestCreate(
        request_number="NEED-1",
        request_date="2026-11-04",
        source_type="need",
        items=[{"asset_type": "battery", "part_name": "بطارية اختبار", "requested_quantity": 1}],
    )
    assert request.source_id is None

    with pytest.raises(ValidationError, match="الاحتياج لا يرتبط"):
        SparePartRequestCreate(
            request_number="NEED-2",
            request_date="2026-11-04",
            source_type="need",
            source_id=1,
            items=[{"part_name": "فلتر", "requested_quantity": 1}],
        )


def test_spare_part_request_item_quantity_constraints():
    checks = {
        c.name: str(c.sqltext)
        for c in SparePartRequestItem.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name
    }

    assert checks["ck_spare_part_request_item_requested_positive"] == "requested_quantity > 0"
    assert checks["ck_spare_part_request_item_received_nonnegative"] == "received_quantity >= 0"
