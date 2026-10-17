from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.spare_parts_movements.schemas import MovementDocumentCreate


def test_return_accepts_received_item_without_distribution_reference():
    data = MovementDocumentCreate(
        document_number="R-1",
        document_type="return",
        document_date=date(2026, 10, 4),
        items=[{
            "request_item_id": 1,
            "received_request_item_id": 1,
            "quantity": 1,
        }],
    )

    assert data.source_document_id is None
    assert data.items[0].received_request_item_id == 1


def test_distribution_does_not_accept_source_document():
    with pytest.raises(ValidationError):
        MovementDocumentCreate(
            document_number="D-1",
            document_type="distribution",
            document_date=date(2026, 10, 4),
            recipient="الورشة",
            source_document_id=10,
            items=[{"request_item_id": 1, "quantity": 1}],
        )


def test_return_recipient_is_derived_not_user_required():
    data = MovementDocumentCreate(
        document_number="R-2",
        document_type="return",
        document_date=date(2026, 10, 4),
        source_document_id=10,
        items=[{"request_item_id": 1, "quantity": 1, "source_item_id": 7}],
    )
    assert data.recipient is None
