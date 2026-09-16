from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
TREE_SCRIPT = Path("static/js/master-data-tree.js").read_text(encoding="utf-8")
MAIN = Path("web/main.py").read_text(encoding="utf-8")


def test_master_data_keeps_excel_import_entry_points_and_reader():
    assert 'id="excelFile"' in TEMPLATE
    assert "xlsx@0.18.5/dist/xlsx.full.min.js" in TEMPLATE
    assert "XLSX.read" in TEMPLATE
    assert 'id="importPositions"' in TEMPLATE
    assert 'id="importSizes"' in TEMPLATE
    assert 'id="importSpecs"' in TEMPLATE


def test_master_data_keeps_model_copy_and_delete_actions():
    assert 'data-copy="{{ m.id }}"' in TEMPLATE
    assert 'data-delete="{{ m.id }}"' in TEMPLATE
    assert "'/equipment-types/models/'+del.dataset.delete+'/delete'" in TEMPLATE
    assert "$('modelForm').action='/equipment-types/models/create'" in TEMPLATE


def test_tree_interaction_layer_is_loaded_without_replacing_editor_workflows():
    assert 'MASTER_DATA_SCRIPT = \'<script src="/static/js/master-data-tree.js"></script>\'' in MAIN
    assert 'request.url.path == "/equipment-types"' in MAIN
    assert "tree.addEventListener('click'" in TREE_SCRIPT
    assert "}, true);" in TREE_SCRIPT
    assert "[data-model-row], [data-model]" in TREE_SCRIPT
    assert "tree-context" in TREE_SCRIPT


def test_tree_arrow_owns_group_toggle_and_stops_legacy_workspace_actions():
    assert "const toggle = event.target.closest('.tree-toggle')" in TREE_SCRIPT
    assert "const group = toggle.closest('.tree-group')" in TREE_SCRIPT
    assert "group.classList.toggle('open')" in TREE_SCRIPT
    assert "event.stopPropagation()" in TREE_SCRIPT
    assert "syncArrows();" in TREE_SCRIPT


def test_search_reveals_matching_nodes_and_every_ancestor_before_one_arrow_sync():
    assert "const revealAncestors = (node)" in TREE_SCRIPT
    assert "const parentNode = group.querySelector(':scope > .tree-node')" in TREE_SCRIPT
    assert "parentNode.hidden = false" in TREE_SCRIPT
    assert "group.classList.add('open')" in TREE_SCRIPT
    assert "node.hidden = !node.textContent.toLocaleLowerCase().includes(query);" in TREE_SCRIPT
    assert "if (!node.hidden) revealAncestors(node);" in TREE_SCRIPT
    assert "searchInput.addEventListener('input'" in TREE_SCRIPT
