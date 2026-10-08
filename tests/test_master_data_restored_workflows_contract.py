from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_PATH = Path("app/modules/equipment_types/templates/master_data_workspace.html")
TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")
TREE_SCRIPT = Path("static/js/master-data-tree.js").read_text(encoding="utf-8")
MAIN = Path("web/main.py").read_text(encoding="utf-8")


def test_master_data_has_no_excel_import_at_all():
    """استيراد Excel حُذف نهائيًا من صفحة مركز البيانات (قرار المستخدم 2026-09-30).

    لم يبقَ في الصفحة ولا زرّ ولا قارئ: لا `excelFile`، ولا سكربت xlsx من
    الشبكة، ولا `XLSX.read`. وبقي استيراد قراءات العدادات في صفحتها
    الخاصة (`/meter-readings`) فهو مسار خادم مستقل ولا علاقة له بهذه الصفحة.

    الأهم في التثبت: الربط بـ onclick على عنصر محذوف يرمي استثناءً يوقف
    بقية السكربت، فتصير كل الأزرار المرتبطة بعده ميتة بصمت.
    """
    for gone in (
        'id="excelFile"',
        "xlsx@0.18.5/dist/xlsx.full.min.js",
        "XLSX.read",
        "function importExcel",
        "importTarget",
        'id="importPositions"',
        'id="importSizes"',
        'id="importSpecs"',
        "$('importPositions').onclick",
        "$('importSizes').onclick",
        "$('importSpecs').onclick",
        "$('excelFile').addEventListener",
    ):
        assert gone not in TEMPLATE, f"بقايا استيراد Excel في الصفحة: {gone}"

    # أزرار التحرير اليدوي ما زالت موجودة (هي البديل عن الاستيراد بالحذف).
    # زرّ «＋ إضافة صف» للمواضع حُذف مع الجدول نفسه (قرار 2026-09-30).
    assert 'id="addPosition"' not in TEMPLATE
    assert 'id="addSize"' in TEMPLATE
    assert 'id="chooseSpecs"' in TEMPLATE


def test_master_data_keeps_model_actions_without_copy():
    assert 'data-copy="{{ m.id }}"' not in TEMPLATE
    assert 'data-delete="{{ m.id }}"' in TEMPLATE
    assert 'function viewModel(id):' in TEMPLATE
    assert 'data-type-model' in TEMPLATE
    assert 'id="editModelBtn"' in TEMPLATE
    assert 'id="freezeModelForm"' in TEMPLATE
    assert 'id="deleteModelForm"' in TEMPLATE
    assert 'نسخ الطراز' not in TREE_SCRIPT
    assert '/freeze' in TREE_SCRIPT and '/unfreeze' in TREE_SCRIPT
    assert 'postDelete(`/equipment-types/models/${encodeURIComponent(del.dataset.delete)}/delete`' in TREE_SCRIPT
