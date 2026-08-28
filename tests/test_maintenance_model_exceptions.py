from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import EquipmentBrand, EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceRule
from app.modules.maintenance.router import effective_rules_for_equipment


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_model_exception_replaces_type_rule_only_for_target_model():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="شاحنات", measurement_unit="km")
        brand = EquipmentBrand(name="TestBrand")
        db.add_all([equipment_type, brand])
        db.flush()

        model_a = EquipmentModel(name="Model A", equipment_type_id=equipment_type.id, brand_id=brand.id)
        model_b = EquipmentModel(name="Model B", equipment_type_id=equipment_type.id, brand_id=brand.id)
        model_c = EquipmentModel(name="Model C", equipment_type_id=equipment_type.id, brand_id=brand.id)
        db.add_all([model_a, model_b, model_c])
        db.flush()

        base_rule = MaintenanceRule(
            name="تغيير الزيت",
            equipment_type_id=equipment_type.id,
            interval_km=Decimal("10000"),
            warning_km=Decimal("500"),
            interval_days=None,
            warning_days=7,
            is_active=True,
        )
        db.add(base_rule)
        db.flush()

        exception_a = MaintenanceRule(
            name=base_rule.name,
            equipment_type_id=equipment_type.id,
            equipment_model_id=model_a.id,
            parent_rule_id=base_rule.id,
            interval_km=Decimal("5000"),
            warning_km=Decimal("250"),
            interval_days=None,
            warning_days=7,
            is_active=True,
        )
        exception_b = MaintenanceRule(
            name=base_rule.name,
            equipment_type_id=equipment_type.id,
            equipment_model_id=model_b.id,
            parent_rule_id=base_rule.id,
            interval_km=Decimal("7000"),
            warning_km=Decimal("300"),
            interval_days=None,
            warning_days=7,
            is_active=False,
        )
        db.add_all([exception_a, exception_b])
        db.commit()

        eq_a = SimpleNamespace(equipment_type_id=equipment_type.id, equipment_model_id=model_a.id)
        eq_b = SimpleNamespace(equipment_type_id=equipment_type.id, equipment_model_id=model_b.id)
        eq_c = SimpleNamespace(equipment_type_id=equipment_type.id, equipment_model_id=model_c.id)

        rules_a = effective_rules_for_equipment(db, eq_a)
        rules_b = effective_rules_for_equipment(db, eq_b)
        rules_c = effective_rules_for_equipment(db, eq_c)

        assert [r.id for r in rules_a] == [exception_a.id]
        assert rules_a[0].interval_km == Decimal("5000")

        assert rules_b == []
        assert [r.id for r in rules_c] == [base_rule.id]
        assert rules_c[0].interval_km == Decimal("10000")
    finally:
        db.close()
