from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_PATH = Path("app/modules/equipment_types/templates/master_data_workspace.html")
TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")
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


def test_tree_script_is_loaded_directly_and_response_injection_is_removed():
    assert '<script src="/static/js/master-data-tree.js"></script>' in TEMPLATE
    assert "MASTER_DATA_SCRIPT" not in MAIN
    assert 'request.url.path == "/equipment-types"' not in MAIN
    assert "tree.addEventListener('click'" in TREE_SCRIPT
    assert "}, true);" in TREE_SCRIPT
    assert "[data-model-row], [data-model]" in TREE_SCRIPT


def test_measurement_unit_is_server_rendered_from_the_existing_allowed_values():
    assert '<template id="typeRefFormTemplate">' in TEMPLATE
    assert '<select name="measurement_unit" required>' in TEMPLATE
    assert '<option value="km">كم</option>' in TEMPLATE
    assert '<option value="hours">ساعات</option>' in TEMPLATE
    assert "MEASUREMENT_UNITS" in Path("app/modules/equipment_types/schemas.py").read_text(encoding="utf-8")


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


def test_uncategorized_type_is_rendered_and_marked_for_explicit_uncategorized_tree_branch():
    """Execute the real Jinja template with a NULL category type; it must remain in the rendered tree input."""
    env = Environment(
        loader=FileSystemLoader([
            str(TEMPLATE_PATH.parent),
            "web/templates",
        ]),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(TEMPLATE_PATH.name)
    request = SimpleNamespace(
        query_params={},
        url=SimpleNamespace(path="/equipment-types"),
    )
    html = template.render(
        request=request,
        types=[SimpleNamespace(id=901, name="نوع تجريبي غير مصنف", category_id=None)],
        categories=[],
        brands=[],
        models=[],
        tire_master_data={},
        spec_definitions=[],
        user=None,
    )
    assert "نوع تجريبي غير مصنف" in html
    assert 'data-category=""' in html
    assert "أنواع عتاد غير مصنّفة" in TREE_SCRIPT
    assert "if (!categoryNode) hasUncategorized = true;" in TREE_SCRIPT
    assert "if (hasUncategorized) categoryChildren.appendChild(uncategorizedGroup);" in TREE_SCRIPT
