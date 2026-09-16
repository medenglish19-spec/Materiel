from pathlib import Path


def test_master_data_tree_layer_is_loaded_for_equipment_types_page():
    source = Path("web/main.py").read_text(encoding="utf-8")
    script = Path("static/js/master-data-tree.js").read_text(encoding="utf-8")

    assert 'MASTER_DATA_SCRIPT = \'<script src="/static/js/master-data-tree.js"></script>\'' in source
    assert 'request.url.path == "/equipment-types"' in source
    assert "tree.addEventListener('click'" in script
    assert "}, true);" in script
    assert "[data-model-row], [data-model]" in script
    assert "tree-context" in script


def test_master_data_tree_layer_does_not_replace_existing_editor_contract():
    template = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")

    for marker in (
        'data-copy="{{ m.id }}"',
        'data-delete="{{ m.id }}"',
        'data-tree-add="position"',
        'data-tree-add="size"',
        "XLSX.read",
        "function searchTree(q)",
    ):
        assert marker in template
