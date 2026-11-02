# -*- coding: utf-8 -*-
"""اختبار سلوكي لـ apply_candidates على قاعدة SQLite حقيقية في الذاكرة (بدل الـ stub)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (registers all mappers)
from app.database.base import Base
from app.modules.equipment_types.models import (
    EquipmentBrand,
    EquipmentCategory,
    EquipmentModel,
    EquipmentModelSpecDefinition,
    EquipmentModelSpecValue,
    EquipmentType,
)


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()


def _seed(db):
    cat = EquipmentCategory(name="حافلات", code="BUS", sort_order=1)
    db.add(cat)
    db.flush()
    brand = EquipmentBrand(name="Hyundai", is_active=True)
    db.add(brand)
    db.flush()
    eq_type = EquipmentType(name="حافلة صغيرة", measurement_unit="كم", category_id=cat.id)
    db.add(eq_type)
    db.flush()
    model = EquipmentModel(name="H100", equipment_type_id=eq_type.id, brand_id=brand.id)
    db.add(model)
    db.flush()
    definition = EquipmentModelSpecDefinition(
        name="قدرة المحرك", code="engine_power", data_type="number", unit="kW", sort_order=1
    )
    db.add(definition)
    db.commit()
    return model.id, definition.id, eq_type.id, cat.id


def test_services_apply_response_format():
    from app.modules.document_import import services
    from app.modules.document_import.schemas import ImportApplyItem

    db = _make_session()
    try:
        model_id, def_id, type_id, cat_id = _seed(db)
        cands = [
            # غير معتمد
            ImportApplyItem(definition_id=def_id, value="150", unit="kW", is_new=False,
                            approved=False, ignored=False, edited=False),
            # جديد معتمد
            ImportApplyItem(definition_id=None, name_found="خاصية جديدة", value="10", unit="kg",
                            is_new=True, approved=True, ignored=False, edited=False),
            # موجود معتمد ومعدّل
            ImportApplyItem(definition_id=def_id, name_found="قدرة المحرك", value="12", unit="kW",
                            is_new=False, approved=True, ignored=False, edited=True, value_edited="12"),
        ]
        res = services.apply_candidates(model_id, cands, db)

        assert "results" in res and "summary" in res
        assert [r["status"] for r in res["results"]] == ["not_approved", "created_definition", "applied"]
        summary = res["summary"]
        assert summary["applied"] == 1
        assert summary["created_definition"] == 1
        assert summary["not_approved"] == 1
        assert sum(summary.values()) == 3

        # القاعدة: قيمتان فقط، والتعريف الجديد بنوع المعدة والفئة
        values = db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=model_id).all()
        assert sorted(v.value for v in values) == ["10", "12"]
        new_def = db.query(EquipmentModelSpecDefinition).filter_by(name="خاصية جديدة").one()
        assert new_def.equipment_type_id == type_id and new_def.category_id == cat_id
        assert new_def.unit == "kg"
    finally:
        db.close()
