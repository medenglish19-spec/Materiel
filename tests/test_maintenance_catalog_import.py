"""Regression checks for maintenance catalog row extraction and review safety.

The coordinate strings below are excerpts copied from the real Micra PDF used
for the functional benchmark; they are not an invented maintenance schedule.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.catalog_import import _micra_items, get_catalog_items, update_catalog_item
from app.modules.maintenance.models import MaintenanceCatalogImport


def test_micra_coordinates_extract_operations_and_base_conditions():
    pages = [
        [
            (50.0, 306.1, "Engine oil (Use recommended oil)"),
            (390.1, 306.2, "R RRR R R RR R R"),
            (50.0, 321.3, "Drive belt(s)"),
            (434.3, 320.2, "I I I I I"),
            (50.0, 336.2, "Intake & exhaust valve clearance"),
            (313.1, 336.2, "See NOTE (1)"),
        ],
        [
            (51.8, 309.8, "Brake & clutch fluid (For level & leaks)"),
            (394.7, 309.0, "I II I I II I I I"),
        ],
        [
            (195.7, 218.5, "Engine oil & engine oil filter"),
            (80.4, 218.4, "C D . .. .. .. .A B"),
            (509.1, 219.6, "Replace"),
            (586.0, 218.5, "Every 7 500km (4 500 miles) or 6 months"),
        ],
    ]
    items = _micra_items(pages, "NISSAN MICRA; then every 45 000km /36 months")
    main = [item for item in items if item["schedule_type"] == "normal"]
    severe = [item for item in items if item["schedule_type"] == "severe_conditions"]
    by_name = {item["operation_name"]: item for item in main}

    assert len(main) == 4
    assert by_name["Engine oil (Use recommended oil)"]["corrected_condition"] == {
        "interval_km": 15000, "interval_days": 365,
    }
    assert by_name["Drive belt(s)"]["corrected_condition"] == {
        "interval_km": 30000, "interval_days": 730,
    }
    assert by_name["Intake & exhaust valve clearance"]["condition_note"].startswith("لا تتطلب العملية دوريًا")
    assert len(severe) == 1
    assert severe[0]["suggested_condition"] == {"interval_km": 7500, "interval_days": 183}
    assert severe[0]["review_state"] == "supplemental"


def test_catalog_item_review_validates_condition_and_is_saved():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        equipment_type = EquipmentType(name="نوع اختبار استيراد كتالوج", measurement_unit="km")
        session.add(equipment_type)
        session.flush()
        model = EquipmentModel(name="Micra اختبار", equipment_type_id=equipment_type.id)
        session.add(model)
        session.flush()
        record = MaintenanceCatalogImport(
            equipment_model_id=model.id, version_number=1, filename="Micra.pdf",
            content_sha256="a" * 64, file_type=".pdf", source_file=b"PDF",
            extracted_text="NISSAN MICRA", items_json=json.dumps([{
                "schedule_type": "normal", "operation_name": "Engine oil",
                "review_state": "needs_review", "corrected_condition": None,
            }]), warnings_json="[]",
        )
        session.add(record)
        session.commit()
        updated = update_catalog_item(session, record, 0, {
            "operation_name": "Engine oil", "review_state": "accepted",
            "corrected_condition": {"interval_km": 15000, "interval_days": 365},
        })
        assert updated["review_state"] == "accepted"
        assert get_catalog_items(record)[0]["corrected_condition"]["interval_km"] == 15000
        with pytest.raises(ValueError, match="أكبر من صفر"):
            update_catalog_item(session, record, 0, {
                "corrected_condition": {"interval_km": 0},
            })
        session.rollback()
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
