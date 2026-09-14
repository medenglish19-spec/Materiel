from app.modules.equipment_types import router


def test_master_data_reference_edit_routes_exist():
    paths = {route.path for route in router.router.routes}
    expected = {
        "/equipment-types/categories/{category_id}/update",
        "/equipment-types/{type_id}/update",
        "/equipment-types/brands/{brand_id}/update",
        "/equipment-types/brands/{brand_id}/toggle",
        "/equipment-types/models/{model_id}/update",
    }
    assert expected.issubset(paths)
