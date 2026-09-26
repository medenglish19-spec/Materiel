from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import EquipmentBrand, EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceOperation, MaintenancePlan, MaintenancePlanOperation
from app.modules.maintenance.services import effective_operations_for_equipment


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_maintenance_operations_are_model_effective_through_active_plans():
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

        operation_a = MaintenanceOperation(name="تغيير الزيت", interval_km=Decimal("5000"), warning_km=Decimal("250"))
        operation_b = MaintenanceOperation(name="فحص الفرامل", interval_km=Decimal("7000"), warning_km=Decimal("300"))
        db.add_all([operation_a, operation_b])
        db.flush()
        plan = MaintenancePlan(name="الخطة الأساسية", equipment_model_id=model_a.id, interval_days=180)
        db.add(plan)
        db.flush()
        db.add(MaintenancePlanOperation(plan_id=plan.id, operation_id=operation_a.id))
        db.commit()

        eq_a = SimpleNamespace(equipment_model_id=model_a.id)
        eq_b = SimpleNamespace(equipment_model_id=model_b.id)
        rows_a = effective_operations_for_equipment(db, eq_a)
        rows_b = effective_operations_for_equipment(db, eq_b)

        assert [row.id for row in rows_a] == [operation_a.id]
        assert rows_b == []
    finally:
        db.close()

def test_maintenance_conditions_workspace_uses_operation_library():
    from pathlib import Path

    template = Path("app/modules/maintenance/templates/maintenance_rules_model_only.html").read_text(encoding="utf-8")
    router = Path("app/modules/maintenance/router.py").read_text(encoding="utf-8")

    assert "const api='/api/maintenance'" in template
    assert "${api}/operations" in template
    assert "${api}/operation-groups" in template
    assert "مكتبة شروط الصيانة الدورية" in template
    assert "إضافة عملية صيانة" in template
    assert "equipment_model_id" not in template
    assert "maintenance/rules/create" not in router
    assert "exceptions/create" not in router
    assert "parent_rule" not in router


def test_maintenance_plan_workspace_is_exposed():
    from pathlib import Path

    template = Path("app/modules/maintenance/templates/maintenance_plans.html").read_text(encoding="utf-8")
    router = Path("app/modules/maintenance/router.py").read_text(encoding="utf-8")
    home = Path("app/modules/maintenance/templates/maintenance_home.html").read_text(encoding="utf-8")

    assert '@router.get("/maintenance/plans"' in router
    assert 'maintenance_plans.html' in router
    assert "api+'/plans'" in template
    assert "api+'/plans/'+id+'/operations'" in template
    assert "خطة صيانة" in template
    assert "/maintenance/plans" in home
