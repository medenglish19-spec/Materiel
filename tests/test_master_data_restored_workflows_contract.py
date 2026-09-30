from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_PATH = Path("app/modules/equipment_types/templates/master_data_workspace.html")
TEMPLATE = TEMPLATE_PATH.read_text(encoding="utf-8")
NAV_SCRIPT = Path("static/js/master-data-nav.js").read_text(encoding="utf-8")
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


def test_master_data_keeps_model_copy_and_delete_actions():
    assert 'data-copy="{{ m.id }}"' in TEMPLATE
    assert 'data-delete="{{ m.id }}"' in TEMPLATE
    assert "postDelete(`/equipment-types/models/${encodeURIComponent(del.dataset.delete)}/delete`" in NAV_SCRIPT
    assert "$('modelForm').action='/equipment-types/models/create'" in TEMPLATE


def test_navigation_script_is_loaded_directly_and_response_injection_is_removed():
    assert '<script src="/static/js/master-data-nav.js' in TEMPLATE
    assert "MASTER_DATA_SCRIPT" not in MAIN
    assert 'request.url.path == "/equipment-types"' not in MAIN
    # التنقّل يملك نقرة واحدة على #nav في طور الالتقاط، فأي «＋» أو «✎» داخل الصف
    # لا يمرّ أيضًا إلى اختيار الصف أو فتحه.
    assert "const nav = document.getElementById('nav');" in NAV_SCRIPT
    assert "if (!nav) return;" in NAV_SCRIPT
    assert "nav.addEventListener('click'" in NAV_SCRIPT
    assert "}, true);" in NAV_SCRIPT
    assert "[data-model-row], [data-model]" not in NAV_SCRIPT


def test_measurement_unit_is_server_rendered_from_the_existing_allowed_values():
    assert '<template id="typeRefFormTemplate">' in TEMPLATE
    assert '<select name="measurement_unit" required>' in TEMPLATE
    assert '<option value="km">كم</option>' in TEMPLATE
    assert '<option value="hours">ساعات</option>' in TEMPLATE
    assert "MEASUREMENT_UNITS" in Path("app/modules/equipment_types/schemas.py").read_text(encoding="utf-8")


def test_tree_arrow_owns_group_toggle_and_stops_legacy_workspace_actions():
    assert "const toggle = event.target.closest('.tree-toggle')" in NAV_SCRIPT
    assert "const group = toggle.closest('.tree-group')" in NAV_SCRIPT
    assert "group.classList.toggle('open')" in NAV_SCRIPT
    assert "event.stopPropagation()" in NAV_SCRIPT
    assert "syncArrows();" in NAV_SCRIPT


def test_search_filters_every_level_and_opens_the_parents_before_one_arrow_sync():
    assert "const search = $('navSearch');" in NAV_SCRIPT
    start = NAV_SCRIPT.index("search?.addEventListener('input'")
    # الفئة/النوع/الطراز: يُخفى ما لا يطابق، ويُفتح ما يطابق حتى تظهر النتيجة،
    # ثم تُضبط الأسهم مرة واحدة بعد الفلترة كلها.
    assert "nav.querySelectorAll('.model-group, .type-group, .mdx-sheet').forEach((group) => {" in NAV_SCRIPT[start:]
    assert "group.hidden = !matches(group);" in NAV_SCRIPT[start:]
    assert "if (query && !group.classList.contains('model-group')) group.classList.add('open');" in NAV_SCRIPT[start:]
    assert NAV_SCRIPT.index("group.hidden = !matches(group);", start) < NAV_SCRIPT.index("syncArrows();", start)
    assert "const matches = (group) => !query || group.textContent.toLocaleLowerCase().includes(query);" in NAV_SCRIPT


def test_model_workspace_switches_real_sections_and_sheet_selection_maps_to_them():
    assert "const selectSection = (index, options = {}) =>" in NAV_SCRIPT
    assert "boxes.forEach((box, i) => { const visible = showAll || i === safe; box.hidden = !visible;" in NAV_SCRIPT
    assert "tab.setAttribute('aria-selected', active ? 'true' : 'false');" in NAV_SCRIPT
    assert "window.MATERIEL_MODEL_WORKSPACE_SELECT = selectSection;" in NAV_SCRIPT
    # فقرة الشرائح تفتح القسم المسمّى نفسه، لا رقمًا مخمَّنًا.
    assert "const sectionMap = { basic: 0, tires: 1, sizes: 1, batteries: 2, specs: 3 };" in NAV_SCRIPT
    assert "window.MATERIEL_MODEL_WORKSPACE_SECTIONS = sectionMap;" in NAV_SCRIPT
    assert "selectSection(sectionMap[model.dataset.section || 'basic'] || 0, { focus: true })" in NAV_SCRIPT
    assert "selectSection(0);" in NAV_SCRIPT


def test_uncategorized_type_gets_its_own_explicit_sheet():
    """نفّذ القالب الحقيقي بنوع بلا فئة؛ يجب أن يظهر في شريحة «غير مصنّفة» لا أن يختفي.

    الشجرة القديمة كانت تبني هذا الفرع في المتصفح عبر متغيّر `hasUncategorized`،
    والقالب اليوم يرسمه صراحةً، فلا خطوة بناء في السكربت.
    """
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
    assert "أنواع عتاد غير مصنّفة" in html
    sheet = html.split('data-sheet="uncategorized"', 1)[1].split("</section>", 1)[0]
    assert "نوع تجريبي غير مصنف" in sheet
    assert "hasUncategorized" not in NAV_SCRIPT
    assert "buildHierarchy" not in NAV_SCRIPT
    # شريحة «غير مصنّفة» تعرض زرّ إنشاء نوع بلا فئة، كسائر الشرائح.
    assert 'class="master-inline-add master-inline-add-type" data-new-ref="type">' in sheet
