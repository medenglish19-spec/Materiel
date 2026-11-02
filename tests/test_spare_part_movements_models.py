from sqlalchemy import CheckConstraint

from app.modules.spare_parts_movements.models import SparePartMovementDocument, SparePartMovementItem


def test_spare_part_movement_models():
    assert SparePartMovementDocument.__tablename__ == "spare_part_movement_documents"
    assert SparePartMovementItem.__tablename__ == "spare_part_movement_items"
    assert "document_number" in SparePartMovementDocument.__table__.columns
    assert "document_type" in SparePartMovementDocument.__table__.columns
    assert "request_item_id" in SparePartMovementItem.__table__.columns
    assert "quantity" in SparePartMovementItem.__table__.columns
    assert "source_document_id" in SparePartMovementDocument.__table__.columns
    assert "source_item_id" in SparePartMovementItem.__table__.columns


def test_movement_constraints():
    checks = {c.name: str(c.sqltext) for c in SparePartMovementDocument.__table__.constraints if isinstance(c, CheckConstraint) and c.name}
    assert checks["ck_spare_part_movement_document_type"] == "document_type IN ('distribution', 'return')"
    item_checks = {c.name: str(c.sqltext) for c in SparePartMovementItem.__table__.constraints if isinstance(c, CheckConstraint) and c.name}
    assert item_checks["ck_spare_part_movement_item_quantity_positive"] == "quantity > 0"
