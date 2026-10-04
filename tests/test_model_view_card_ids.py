"""بطاقة عرض الطراز: كل معرّف تكتبه viewModel يجب أن يكون موجوداً فعلاً.

العلامة: `master-data-tree.js` يستدعي `window.viewModel(id)` عند النقر على صف
الطراز. Inside `viewModel` كل `$('someId')` غير معرَّف يُرجع null، وأول
`null.textContent = ...` يرمي TypeError **قبل** `show($('modelViewPanel'))` —
فتظهر رسالة "لا يحدث شيء عند الضغط على الطراز" بينما النوع يعمل.

هذا الاختبار يمسك الصنف كله: أي معرّف يمرّ إلى $() في سكربتات الصفحة ولا
وجود له في HTML يُعدّ معرّفاً مفقوداً.
"""
import re
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "modules"
    / "equipment_types"
    / "templates"
    / "master_data_workspace.html"
)
TREE_JS = Path(__file__).resolve().parents[1] / "static" / "js" / "master-data-tree.js"


def _source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_every_id_used_by_the_page_script_exists_in_the_markup():
    source = _source()
    declared = set(re.findall(r'id="([A-Za-z][\w:-]*)"', source))

    script = source[source.index("<script>") :]
    used = set(re.findall(r"\$\('([^']+)'\)", script))
    used |= set(re.findall(r"getElementById\('([^']+)'\)", script))
    used |= set(re.findall(r"\$\(`([^`$]+)`\)", script))

    missing = sorted(i for i in used if i and i not in declared)
    assert not missing, (
        "معرّفات تستدعيها سكربتات الصفحة ولا وجود لها في HTML — أول واحد منها "
        f"يُسقط viewModel قبل show(): {missing}"
    )


def test_freeze_and_delete_buttons_keep_their_ids():
    """السبب المباشر للحالة: زرّان بلا id كان viewModel يتوقّعهما."""
    source = _source()
    assert 'id="freezeModelBtn"' in source, "زرّ التجميد بلا id"
    assert 'id="deleteModelBtn"' in source, "زرّ الحذف بلا id"


def test_model_row_carries_the_id_the_tree_javascript_hands_to_view_model():
    """master-data-tree.js يقرأ data-model-row ويمرّره إلى viewModel."""
    assert 'data-model-row="{{ m.id }}"' in _source()
    assert "window.viewModel(row.dataset.modelRow)" in TREE_JS.read_text(encoding="utf-8")
