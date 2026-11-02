"""Regression checks for maintenance catalog row extraction and review safety.

The coordinate strings below are excerpts copied from the real Micra PDF used
for the functional benchmark; they are not an invented maintenance schedule.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.core.dependencies import get_current_user
from app.database import session as session_module
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.catalog_import import _micra_items, _versa_items, get_catalog_items, update_catalog_item
from app.modules.maintenance.models import (
    MaintenanceCatalogImport, MaintenanceModelOperation, MaintenanceOperation,
    maintenance_operation_models,
)
from app.modules.maintenance.router import maintenance_catalog_apply, router as maintenance_router
from app.modules.users.models import User


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
    assert by_name["Replace engine oil (Use recommended oil)"]["source_operation_name"] == "Engine oil (Use recommended oil)"
    assert by_name["Replace engine oil (Use recommended oil)"]["operation_action"] == "replacement"
    assert by_name["Replace engine oil (Use recommended oil)"]["corrected_condition"] == {
        "interval_km": 15000, "interval_days": 365,
    }
    assert by_name["Inspect drive belt(s)"]["source_operation_name"] == "Drive belt(s)"
    assert by_name["Inspect drive belt(s)"]["corrected_condition"] == {
        "interval_km": 30000, "interval_days": 730,
    }
    assert by_name["Intake & exhaust valve clearance"]["condition_note"].startswith("لا تتطلب العملية دوريًا")
    assert len(severe) == 1
    assert severe[0]["suggested_condition"] == {"interval_km": 7500, "interval_days": 183}
    assert severe[0]["review_state"] == "supplemental"


def test_versa_columns_keep_source_names_profiles_and_both_interval_axes():
    pages = [[
        (23.4, 526.0, "1.6L 4 CYLINDER HR16DE maintenance schedule"),
        (23.4, 480.0, "5,000 miles/(8,000 km)/6 months"),
        (23.4, 465.0, "Standard maintenance:"),
        (23.4, 450.0, "Not Applicable. Proceed to next interval"),
        (23.4, 435.0, "Severe maintenance:"),
        (23.4, 420.0, "Inspections:"),
        (23.4, 405.0, "• Brake pads & rotors"),
        (210.5, 480.0, "7,500 miles/(12,000 km)/6 months"),
        (210.5, 465.0, "Standard maintenance:"),
        (210.5, 450.0, "Essential:"),
        (210.5, 435.0, "• Replace engine oil & filter"),
        (210.5, 420.0, "Severe maintenance:"),
        (210.5, 405.0, "Not Applicable. Proceed to next interval"),
    ]]

    items, source_pages = _versa_items(pages)

    assert source_pages == [1]
    assert [(item["operation_name"], item["schedule_type"]) for item in items] == [
        ("Inspect brake pads & rotors", "severe_conditions"),
        ("Replace engine oil & filter", "normal"),
    ]
    assert items[0]["source_operation_name"] == "Brake pads & rotors"
    assert items[0]["operation_action"] == "inspection"
    assert items[0]["corrected_condition"] == {"interval_km": 8000, "interval_days": 183}
    assert items[1]["source_interval"] == {
        "miles": 7500, "km": 12000, "months": 6, "raw": "7,500 miles/(12,000 km)/6 months",
    }
    assert items[0]["operation_name"] == "Inspect brake pads & rotors"  # action is explicit; source wording is retained separately


def test_versa_continuation_page_inherits_previous_standard_interval():
    pages = [
        [
            (23.4, 526.0, "1.6L 4 CYLINDER HR16DE maintenance schedule"),
            (23.4, 480.0, "120,000 miles/(192,000 km)/96 months"),
            (23.4, 465.0, "Standard maintenance:"),
            (23.4, 450.0, "Inspections:"),
            (23.4, 435.0, "• Brake pads and rotors"),
        ],
        [
            (23.4, 526.0, "Essential:"),
            (23.4, 510.0, "• Replace engine oil & filter"),
            (23.4, 495.0, "Severe maintenance:"),
            (23.4, 480.0, "Not Applicable. Proceed to next interval"),
        ],
    ]

    items, source_pages = _versa_items(pages)

    continued = next(item for item in items if item["source_page"] == 2)
    assert 2 in source_pages
    assert continued["operation_name"] == "Replace engine oil & filter"
    assert continued["schedule_type"] == "normal"
    assert continued["source_interval"]["km"] == 192000


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


def test_applying_import_creates_operation_scoped_only_to_selected_model():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        equipment_type = EquipmentType(name="نوع اختبار نطاق الاستيراد", measurement_unit="km")
        session.add(equipment_type)
        session.flush()
        micra = EquipmentModel(name="Micra نطاق", equipment_type_id=equipment_type.id)
        other_model = EquipmentModel(name="طراز آخر نطاق", equipment_type_id=equipment_type.id)
        session.add_all([micra, other_model])
        session.flush()

        general = MaintenanceOperation(name="تغيير زيت المحرك", is_active=True)
        general.equipment_models.append(other_model)
        record = MaintenanceCatalogImport(
            equipment_model_id=micra.id, version_number=1, filename="Micra.pdf",
            content_sha256="b" * 64, file_type=".pdf", source_file=b"PDF",
            extracted_text="NISSAN MICRA", warnings_json="[]", status="draft",
            items_json=json.dumps([{
                "schedule_type": "normal", "operation_name": general.name,
                "review_state": "accepted", "corrected_condition": {"interval_km": 15000},
                "condition_note": None, "source_page": 1,
            }], ensure_ascii=False),
        )
        session.add_all([general, record])
        session.commit()
        general_id = general.id

        maintenance_catalog_apply(record.id, session, None)

        scoped = session.query(MaintenanceModelOperation).filter_by(
            name="تغيير زيت المحرك", equipment_model_id=micra.id,
        ).one()
        assert scoped.equipment_model_id == micra.id
        assert scoped.interval_km == 15000
        assert session.query(MaintenanceOperation).filter_by(id=general_id).one().name == "تغيير زيت المحرك"
        assert session.execute(maintenance_operation_models.select().where(
            maintenance_operation_models.c.operation_id == general_id,
        )).all()[0].equipment_model_id == other_model.id
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_applying_schedule_variants_preserves_each_interval_and_profile():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        equipment_type = EquipmentType(name="نوع اختبار جداول الصيانة", measurement_unit="km")
        session.add(equipment_type)
        session.flush()
        model = EquipmentModel(name="Nissan Versa جدول", equipment_type_id=equipment_type.id)
        session.add(model)
        session.flush()
        record = MaintenanceCatalogImport(
            equipment_model_id=model.id, version_number=1, filename="Versa.pdf",
            content_sha256="c" * 64, file_type=".pdf", source_file=b"PDF",
            extracted_text="Nissan Versa", warnings_json="[]", status="draft",
            items_json=json.dumps([
                {
                    "schedule_type": "normal", "operation_name": "Replace engine oil & filter",
                    "review_state": "accepted", "corrected_condition": {"interval_km": 12000, "interval_days": 183},
                    "source_interval": {"raw": "7,500 miles/(12,000 km)/6 months"}, "source_page": 455,
                },
                {
                    "schedule_type": "severe_conditions", "operation_name": "Replace engine oil & filter",
                    "review_state": "accepted", "corrected_condition": {"interval_km": 8000, "interval_days": 183},
                    "source_interval": {"raw": "5,000 miles/(8,000 km)/6 months"}, "source_page": 454,
                },
            ], ensure_ascii=False),
        )
        session.add(record)
        session.commit()

        maintenance_catalog_apply(record.id, session, None)

        operations = session.query(MaintenanceModelOperation).filter_by(
            name="Replace engine oil & filter", equipment_model_id=model.id,
        ).all()
        assert len(operations) == 2
        intervals = {
            operation.description.split("سياق الجدول: ", 1)[1].split(" |", 1)[0]: session.execute(
                select(MaintenanceModelOperation.interval_km).where(MaintenanceModelOperation.id == operation.id)
            ).scalar_one()
            for operation in operations
        }
        assert intervals["الجدول القياسي"] == 12000
        assert intervals["جدول الظروف القاسية"] == 8000
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_catalog_review_page_paginates_filters_and_bulk_reviews_selected_rows():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار صفحة مراجعة Versa", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="Nissan Versa مراجعة", equipment_type_id=equipment_type.id)
        user = User(id=91, username="catalog-review-test", full_name="مراجع", hashed_password="x", role="admin", is_active=True)
        db.add_all([model, user])
        db.flush()
        items = [{
            "schedule_type": "normal", "section": "standard_maintenance",
            "operation_name": f"Replace engine oil & filter {index}",
            "source_page": 454 + index // 3,
            "source_interval": {"miles": 7500, "km": 12000, "months": 6, "raw": "7,500 miles/(12,000 km)/6 months"},
            "source_excerpt": "Standard maintenance | Essential | Replace engine oil & filter",
            "corrected_condition": {"interval_km": 12000, "interval_days": 183},
            "condition_note": "Use whichever comes first.", "review_state": "needs_review",
        } for index in range(45)]
        record = MaintenanceCatalogImport(
            equipment_model_id=model.id, version_number=1, filename="Versa.pdf",
            content_sha256="d" * 64, file_type=".pdf", source_file=b"PDF",
            extracted_text="PAGE 454: Versa maintenance schedule", items_json=json.dumps(items), warnings_json="[]",
        )
        db.add(record)
        db.commit()
        catalog_id = record.id

        app = FastAPI()
        app.include_router(maintenance_router)

        def override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[session_module.get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: user
        with TestClient(app) as client:
            second_page = client.get(f"/maintenance/catalog-imports/{catalog_id}?page=2")
            assert second_page.status_code == 200
            assert "صفحة 2 من 2" in second_page.text
            assert "Replace engine oil &amp; filter 40" in second_page.text
            assert "Replace engine oil &amp; filter 39" not in second_page.text

            filtered = client.get(f"/maintenance/catalog-imports/{catalog_id}?q=filter%2043&schedule_type=normal")
            assert filtered.status_code == 200
            assert "Replace engine oil &amp; filter 43" in filtered.text
            assert "Replace engine oil &amp; filter 42" not in filtered.text

            reviewed = client.post(
                f"/maintenance/catalog-imports/{catalog_id}/review-selection",
                data={"item_indices": ["40", "41"], "review_state": "accepted", "page": "2"},
                follow_redirects=False,
            )
            assert reviewed.status_code == 303, reviewed.text
            db.expire_all()
            saved_items = get_catalog_items(db.get(MaintenanceCatalogImport, catalog_id))
            assert [saved_items[index]["review_state"] for index in (40, 41)] == ["accepted", "accepted"]
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
