from pathlib import Path


TEMPLATE = Path("app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")


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


def test_search_expands_matching_ancestors_instead_of_only_filtering_rows():
    start = TEMPLATE.index("function searchTree(q)")
    end = TEMPLATE.index("function importExcel", start)
    script = TEMPLATE[start:end]
    assert "g.classList.add('open')" in script
    assert "const parent=g.parentElement?.closest('.tree-group')" in script
    assert "parent.querySelector(':scope > .tree-node')" in script
