from pathlib import Path


def test_master_data_reference_forms_have_explicit_post_actions():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    assert 'action="/equipment-types/categories/create"' in template
    assert 'action="/equipment-types/create"' in template
    assert 'action="/equipment-types/brands/create"' in template
    assert 'method="post"' in template


def test_new_model_button_does_not_scroll_page_and_focuses_first_field():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    assert "window.scrollTo" not in template
    assert "$('modelName').focus()" in template
    assert 'id="newModelTop"' in template
