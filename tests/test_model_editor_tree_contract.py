from pathlib import Path


def _template() -> str:
    return Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")


def test_model_tree_has_nested_tire_branch():
    template = _template()
    model_start = template.index('<div class="tree-group model-tree-item"')
    model_end = template.index('{% endfor %}', model_start)
    block = template[model_start:model_end]
    tire = block.index('data-section="tires"')
    positions = block.index('data-section="positions"', tire)
    sizes = block.index('data-section="sizes"', positions)
    batteries = block.index('data-section="batteries"', sizes)
    tire_wrapper = block.rfind('<div class="tree-group">', 0, tire)
    assert tire_wrapper >= 0
    tire_branch = block[tire_wrapper:batteries]
    assert '<div class="tree-children">' in tire_branch
    assert 'class="tree-toggle"' in tire_branch
    assert positions < sizes < batteries


def test_model_editor_keeps_subsections_under_model():
    template = _template()
    start = template.index('<div class="tree-group model-tree-item"')
    end = template.index('{% endfor %}', start)
    block = template[start:end]
    for section in ("basic", "tires", "positions", "sizes", "batteries", "specs"):
        assert f'data-section="{section}"' in block
    assert block.count('class="tree-children"') >= 2


def test_model_delete_form_is_present():
    template = _template()
    assert 'id="deleteModelForm"' in template
    assert 'method="post"' in template[template.index('id="deleteModelForm"'):]


# Keep CI verification attached to the corrected tree contract commit.
