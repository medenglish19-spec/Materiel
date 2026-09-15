from pathlib import Path


def test_model_tree_has_nested_tire_branch():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    tire = template.index('data-section="tires"')
    positions = template.index('data-section="positions"', tire)
    sizes = template.index('data-section="sizes"', positions)
    batteries = template.index('data-section="batteries"', sizes)
    block = template[tire:batteries]
    assert '<div class="tree-group">' in block
    assert '<div class="tree-children">' in block
    assert 'class="tree-toggle"' in block
    assert positions < sizes < batteries


def test_model_editor_keeps_subsections_under_model():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    start = template.index('class="model-tree-item"')
    end = template.index('{% else %}', start)
    block = template[start:end]
    for section in ("basic", "tires", "positions", "sizes", "batteries", "specs"):
        assert f'data-section="{section}"' in block
    assert block.count('class="tree-children"') >= 2


def test_model_delete_form_is_present():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
    assert 'id="deleteModelForm"' in template
    assert 'method="post"' in template[template.index('id="deleteModelForm"'):]
