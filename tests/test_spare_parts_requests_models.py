from sqlalchemy import CheckConstraint
from app.modules.spare_parts_requests.models import SparePartRequest, SparePartRequestItem


def test_spare_part_request_model_contract():
    assert SparePartRequest.__tablename__ == "spare_part_requests"
    assert SparePartRequestItem.__tablename__ == "spare_part_request_items"
    for name in ("source_type", "maintenance_record_id", "repair_id", "tire_id", "battery_id", "equipment_id", "status"):
        assert name in SparePartRequest.__table__.columns
    for name in ("request_id", "spare_part_id", "requested_quantity", "approved_quantity", "issued_quantity"):
        assert name in SparePartRequestItem.__table__.columns


def test_spare_part_request_source_and_status_constraints():
    checks = {c.name: str(c.sqltext) for c in SparePartRequest.__table__.constraints if isinstance(c, CheckConstraint) and c.name}
    assert "ck_spare_part_request_source_type" in checks
    assert "maintenance" in checks["ck_spare_part_request_source_type"]
    assert "repair" in checks["ck_spare_part_request_source_type"]
    assert "tire" in checks["ck_spare_part_request_source_type"]
    assert "battery" in checks["ck_spare_part_request_source_type"]
    assert "ck_spare_part_request_source_match" in checks
    assert "ck_spare_part_request_status" in checks


def test_spare_part_request_item_quantity_constraints():
    checks = {c.name: str(c.sqltext) for c in SparePartRequestItem.__table__.constraints if isinstance(c, CheckConstraint) and c.name}
    assert checks["ck_spare_part_request_item_requested_positive"] == "requested_quantity > 0"
    assert "approved_quantity <= requested_quantity" in checks["ck_spare_part_request_item_approved_lte_requested"]
    assert "issued_quantity <= approved_quantity" in checks["ck_spare_part_request_item_issued_lte_approved"]
