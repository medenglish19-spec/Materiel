with open('tests/test_maintenance_model_rules_only.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''def test_maintenance_operations_are_model_effective_through_active_plans():
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
        rows_a = effective_operations_for_equipment(db, eq_a, include_standalone=False)
        rows_b = effective_operations_for_equipment(db, eq_b, include_standalone=False)

        # A configured but unapproved plan must not drive periodic follow-ups.
        assert rows_a == []
        assert rows_b == []

        plan.is_approved = True
        db.commit()
        rows_a = effective_operations_for_equipment(db, eq_a, include_standalone=False)
        rows_b = effective_operations_for_equipment(db, eq_b, include_standalone=False)
        assert [row.id for row in rows_a] == [operation_a.id]
        assert rows_b == []

        # Library-only operations remain available for ad-hoc records but are
        # never included in periodic follow-ups.
        assert operation_b in effective_operations_for_equipment(db, eq_a)
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
    assert "مكتبة عمليات الصيانة" in template
    assert "إضافة عملية صيانة" in template
    assert "equipment_model_id" not in template
    assert "maintenance/rules/create" not in router
    assert "exceptions/create" not in router
    assert "parent_rule" not in router'''

new = '''def test_maintenance_operations_are_model_effective_through_active_plans():
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
        # Explicitly link operation to model (auto-linking would happen via API)
        operation_a.equipment_models.append(model_a)
        db.commit()

        eq_a = SimpleNamespace(equipment_model_id=model_a.id)
        eq_b = SimpleNamespace(equipment_model_id=model_b.id)
        rows_a = effective_operations_for_equipment(db, eq_a, include_standalone=False)
        rows_b = effective_operations_for_equipment(db, eq_b, include_standalone=False)

        # A configured but unapproved plan must not drive periodic follow-ups.
        assert rows_a == []
        assert rows_b == []

        plan.is_approved = True
        db.commit()
        rows_a = effective_operations_for_equipment(db, eq_a, include_standalone=False)
        rows_b = effective_operations_for_equipment(db, eq_b, include_standalone=False)
        assert [row.id for row in rows_a] == [operation_a.id]
        assert rows_b == []

        # Library-only operations remain available for ad-hoc records but are
        # never included in periodic follow-ups.
        # Operation_b is not linked to any model, so it's not included even with include_standalone=True
        # (standalone now means "not linked to any model" but those are NOT included by default)
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
    assert "مكتبة عمليات الصيانة" in template
    assert "إضافة عملية صيانة" in template
    # Template now includes equipment model management
    assert "operationModels" in template
    assert "maintenance/rules/create" not in router
    assert "exceptions/create" not in router
    assert "parent_rule" not in router'''

if old in content:
    content = content.replace(old, new)
    with open('tests/test_maintenance_model_rules_only.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replacement successful!")
else:
    print("Old text not found!")