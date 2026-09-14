import pytest

from app.modules.asset_movements.mandatory_removal import require_explicit_removal, require_free_before_install


def test_remove_requires_reason():
    with pytest.raises(ValueError, match="سبب فك الإطار إلزامي"):
        require_explicit_removal("remove", "", resource_label="الإطار")


def test_move_is_not_a_direct_operation():
    with pytest.raises(ValueError, match="نقل البطارية المباشر غير مسموح"):
        require_explicit_removal("move", "نقل", resource_label="البطارية")


def test_install_requires_removal_when_resource_is_installed():
    with pytest.raises(ValueError, match="فك البطارية"):
        require_free_before_install(movement_type="install", currently_installed=True, resource_label="البطارية")


def test_install_is_allowed_when_resource_is_free():
    require_free_before_install(movement_type="install", currently_installed=False, resource_label="البطارية")


def test_install_reason_is_not_required_by_policy():
    require_explicit_removal("install", "", resource_label="الإطار")
