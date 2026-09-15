from pathlib import Path


def _template() -> str:
    return Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")


def test_model_tree_has_nested_tire_branch():
    template = _template()
    model_start = template.index('<div class="tree-group model-group">')
    model_end = template.index('{% endfor %}', model_start)
    block = template[model_start:model_end]
    tire = block.index('data-section="tires"')
    positions = block.index('data-section="positions"', tire)
    sizes = block.index('data-section="sizes"', positions)
    batteries = block.index('data-section="batteries"', sizes)
    assert positions < sizes < batteries
    assert 'class="children"' in block[tire:batteries]


def test_model_editor_keeps_subsections_under_model():
    template = _template()
    start = template.index('<div class="tree-group model-group">')
    end = template.index('{% endfor %}', start)
    block = template[start:end]
    for section in ("basic", "tires", "positions", "sizes", "batteries", "specs"):
        assert f'data-section="{section}"' in block
    assert block.count('class="children"') >= 2


def test_master_data_tree_owns_reference_creation_actions():
    template = _template()
    for kind in ("category", "type", "brand", "spec", "model"):
        assert f'data-add="{kind}"' in template
        assert f'data-new-ref="{kind}"' in template
    assert 'id="newModelTop"' not in template
    assert 'id="importExcelBtn"' not in template


def test_master_data_tree_keeps_model_copy_and_delete_actions():
    template = _template()
    assert 'data-copy="{{ m.id }}"' in template
    assert 'data-delete="{{ m.id }}"' in template
    assert "'/equipment-types/models/'+del.dataset.delete+'/delete'" in template
