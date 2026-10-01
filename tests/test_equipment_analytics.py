from types import SimpleNamespace

from app.modules.equipment.analytics import build_capacity_readiness_analysis


def _item(type_name, theoretical, condition="ready", operational="available", model="M1"):
    category = SimpleNamespace(name="نقل الأشخاص")
    equipment_type = SimpleNamespace(
        name=type_name,
        theoretical_quantity=theoretical,
        category=category,
    )
    brand = SimpleNamespace(name="Test")
    equipment_model = SimpleNamespace(name=model, brand=brand)
    return SimpleNamespace(
        equipment_type=equipment_type,
        equipment_model=equipment_model,
        technical_condition=condition,
        operational_status=operational,
    )


def test_capacity_readiness_keeps_requirement_at_type_level():
    result = build_capacity_readiness_analysis([
        _item("حافلة", 2, "ready", "available", "H1"),
        _item("حافلة", 2, "broken", "in_maintenance", "H1"),
    ])

    assert result["totals"]["theoretical"] == 2
    assert result["totals"]["actual"] == 2
    assert result["totals"]["need"] == 0
    assert result["totals"]["broken"] == 1

    type_row = result["categories"][0]["types"][0]
    assert type_row["theoretical"] == 2
    assert type_row["need"] == 0

    model = type_row["models"][0]
    assert model["actual"] == 2
    assert "theoretical" not in model


def test_capacity_readiness_separates_undefined_requirement_and_operational_constraint():
    result = build_capacity_readiness_analysis([
        _item("شاحنة", 0, "ready", "in_mission", "T1"),
        _item("شاحنة", 0, "ready_restricted", "unavailable", "T1"),
    ])

    totals = result["totals"]
    assert totals["theoretical"] == 0
    assert totals["need"] == 0
    assert totals["outside_requirement"] == 2
    assert totals["technical_but_not_available"] == 1

    states = {finding["state"] for finding in result["findings"]}
    assert "متطلبات غير محددة" in states
    assert "قيد تشغيلي" in states
