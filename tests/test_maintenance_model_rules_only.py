from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment_types.models import EquipmentBrand, EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceOperation, MaintenancePlan, MaintenancePlanOperation, maintenance_operation_models
from app.modules.maintenance.services import CONDITION_MODEL, effective_operations_for_equipment, operation_condition_for_model


def link_condition(db, operation, model, **condition):
    """Create the operation↔model relation with that model's own condition."""
    db.execute(
        maintenance_operation_models.insert().values(
            operation_id=operation.id,
            equipment_model_id=model.id,
            condition_source=CONDITION_MODEL,
            **condition,
        )
    )


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
        # الشرط يخص الطراز: يُكتب على علاقة العملية بالطراز، لا على العملية.
        link_condition(db, operation_a, model_a, interval_km=Decimal("5000"), warning_km=Decimal("250"))
        db.commit()

        eq_a = SimpleNamespace(equipment_model_id=model_a.id)
        eq_b = SimpleNamespace(equipment_model_id=model_b.id)
        rows_a = effective_operations_for_equipment(db, eq_a, include_standalone=False)
        rows_b = effective_operations_for_equipment(db, eq_b, include_standalone=False)

        # In the new architecture, operation-model link is separate from plan approval.
        # Operation A is linked to Model A, so it's effective for Model A equipment
        # regardless of plan approval status.
        assert [row.id for row in rows_a] == [operation_a.id]
        assert rows_b == []

        # Plan approval still required for plan execution
        plan.is_approved = True
        db.commit()
        rows_a = effective_operations_for_equipment(db, eq_a, include_standalone=False)
        rows_b = effective_operations_for_equipment(db, eq_b, include_standalone=False)
        assert [row.id for row in rows_a] == [operation_a.id]
        assert rows_b == []

        # Library-only operations (not linked to any model) are never included
        assert operation_b not in effective_operations_for_equipment(db, eq_a)
        assert operation_b not in effective_operations_for_equipment(db, eq_a, include_standalone=False)
    finally:
        db.close()


def test_maintenance_conditions_workspace_uses_operation_library():
    from pathlib import Path

    template = Path("app/modules/maintenance/templates/maintenance_rules_model_only.html").read_text(encoding="utf-8")
    router = Path("app/modules/maintenance/router.py").read_text(encoding="utf-8")

    assert "const api='/api/maintenance'" in template
    assert "${api}/operations" in template
    assert "${api}/operation-groups" in template
    assert "مكتبة عمليات الصيانة" in template or "مكتبة شروط الصيانة" in template
    assert "إضافة عملية صيانة" in template
    # شرط الاستحقاق وإعداد الإنذار يُضبطان لكل طراز على حدة، لا مرة واحدة للعملية.
    assert "equipment_model_conditions" in template
    assert "editorModelsBody" in template
    assert "الشرط غير محدد" in template
    assert "conditionDetails" in template
    assert "maintenance/rules/create" not in router
    assert "exceptions/create" not in router
    assert "parent_rule" not in router


def test_operation_condition_is_read_from_the_model_relation():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع شروط الطراز", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model_a = EquipmentModel(name="Model A", equipment_type_id=equipment_type.id)
        model_b = EquipmentModel(name="Model B", equipment_type_id=equipment_type.id)
        db.add_all([model_a, model_b])
        db.flush()
        operation = MaintenanceOperation(name="تغيير زيت المحرك", interval_km=Decimal("5000"))
        db.add(operation)
        db.flush()
        link_condition(db, operation, model_a, interval_km=Decimal("5000"), warning_km=Decimal("250"))
        link_condition(db, operation, model_b, interval_km=Decimal("9000"), warning_km=Decimal("600"))
        db.commit()

        condition_a = operation_condition_for_model(db, operation.id, model_a.id)
        condition_b = operation_condition_for_model(db, operation.id, model_b.id)
        assert (condition_a.interval_km, condition_a.warning_km) == (Decimal("5000.0"), Decimal("250.0"))
        assert (condition_b.interval_km, condition_b.warning_km) == (Decimal("9000.0"), Decimal("600.0"))

        # طراز بلا علاقة => شرط غير محدد، ولا تُستنتج له قيمة من طراز آخر ولا من العملية.
        model_c = EquipmentModel(name="Model C", equipment_type_id=equipment_type.id)
        db.add(model_c)
        db.commit()
        condition_c = operation_condition_for_model(db, operation.id, model_c.id)
        assert condition_c.is_defined is False
        assert condition_c.interval_km is None
    finally:
        db.close()


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