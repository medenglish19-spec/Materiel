import inspect


def test_tire_configuration_cannot_lower_required_positions_below_defined_positions():
    from app.modules.equipment_types import services

    source = inspect.getsource(services.update_model_tire_configuration)

    assert "configured_count" in source
    assert "tire_positions_required<configured_count" in source
    assert "لا يمكن أن يكون أقل من المواضع المعرفة حاليًا" in source


def test_tire_configuration_cannot_disable_tires_with_defined_positions():
    from app.modules.equipment_types import services

    source = inspect.getsource(services.update_model_tire_configuration)

    assert "not has_tires and configured_count" in source
    assert "احذف المواضع أولًا للحفاظ على اتساق الإعدادات" in source
