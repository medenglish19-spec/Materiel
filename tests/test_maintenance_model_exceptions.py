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


def test_maintenance_rules_are_selected_by_model_only():
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
        db.add_all([model_a, model_b])
        db.flush()

        legacy_type_rule = MaintenanceRule(
            name="قاعدة قديمة",
            equipment_type_id=equipment_type.id,
            interval_km=Decimal("10000"),
            warning_km=Decimal("500"),
            is_active=False,
        )
        rule_a = MaintenanceRule(
            name="تغيير الزيت",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model_a.id,
            interval_km=Decimal("5000"),
            warning_km=Decimal("250"),
            is_active=True,
        )
        rule_b = MaintenanceRule(
            name="تغيير الزيت",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model_b.id,
            interval_km=Decimal("7000"),
            warning_km=Decimal("300"),
            is_active=True,
        )
        db.add_all([legacy_type_rule, rule_a, rule_b])
        db.commit()

        eq_a = SimpleNamespace(equipment_type_id=equipment_type.id, equipment_model_id=model_a.id)
        eq_b = SimpleNamespace(equipment_type_id=equipment_type.id, equipment_model_id=model_b.id)
        eq_without_model = SimpleNamespace(equipment_type_id=equipment_type.id, equipment_model_id=None)

        rules_a = effective_rules_for_equipment(db, eq_a)
        rules_b = effective_rules_for_equipment(db, eq_b)

        assert [r.id for r in rules_a] == [rule_a.id]
        assert rules_a[0].interval_km == Decimal("5000")
        assert [r.id for r in rules_b] == [rule_b.id]
        assert rules_b[0].interval_km == Decimal("7000")
        assert effective_rules_for_equipment(db, eq_without_model) == []
    finally:
        db.close()
