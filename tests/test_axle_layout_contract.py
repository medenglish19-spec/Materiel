"""عقد شاشة إنشاء/تعديل الطراز: اختيار نوع عجلات كل محور وتوليد المواضع منه.

قرار المستخدم (2026-09-30): بدل إدخال «عدد الإطارات» رقمًا واحدًا، يُكتب عدد
المحاور ويُختار لكل محور «مفرد» أو «مزدوج»، فيولّد النظام المواضع فورًا:
مفرد = موضع لكل جهة (٢ للمحور) · مزدوج = داخلي + خارجي لكل جهة (٤ للمحور).
مثال المستخدم: ٣ محاور (مفرد، مزدوج، مزدوج) = ١٠ مواضع.

والمشكلة التي سبّبت هذه الشاشة: القسم لم يكن قابلًا للوصول أصلًا، لأن
`editModel` لم يكن يعرض صندوق الإطارات، ولم يكن في الصفحة شريط تنقّل بين
الأقسام. الاختبارات هنا تثبت وجود الأجزاء التي تجعل القسم قابلًا للوصول.
"""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "app/modules/equipment_types/templates/master_data_workspace.html").read_text(encoding="utf-8")
NAV_SCRIPT = (ROOT / "static/js/master-data-nav.js").read_text(encoding="utf-8")
STYLE = (ROOT / "static/css/style.css").read_text(encoding="utf-8")


def _count_axle_wheel_radios(template: str) -> set:
    return set(re.findall(r'name="axle-wheel-\$\{n\}" value="(\w+)"', template))


def test_axle_wheel_picker_markup_exists_in_tires_box():
    assert 'id="axleWheelBody"' in TEMPLATE
    assert 'id="axleWheelHint"' in TEMPLATE
    assert 'id="positionsSummary"' in TEMPLATE
    # الجدول داخل صندوق الإطارات (وهو القسم الذي كان غير قابل للوصول)
    tires_box = TEMPLATE.split('id="tiresEditorBox"', 1)[1].split('data-workspace-section="batteries"', 1)[0]
    assert 'id="axleWheelBody"' in tires_box
    assert 'id="addSize"' in tires_box


def test_axle_wheel_picker_offers_exactly_single_and_dual():
    assert _count_axle_wheel_radios(TEMPLATE) == {"single", "dual"}
    # القاعدة نفسها في جافاسكربت (single = نوع واحد، dual = داخلي ثم خارجي)
    assert "const WHEEL_CHOICE_TYPES={single:['single'],dual:['inner','outer']};" in TEMPLATE
    assert "const AXLE_SIDE_ORDER=['right','left'];" in TEMPLATE


def test_positions_are_generated_automatically_on_any_change():
    # تغيير الاختيار يولّد، وعدد المحاور يولّد، والمقاسات تبقى قابلة للتحرير يدويًا
    assert "r.addEventListener('change',sync)" in TEMPLATE
    assert "$('axleCount').addEventListener('input'" in TEMPLATE
    assert 'id="addSize"' in TEMPLATE
    # زر «＋ إضافة صف» للمقاسات لم يكن يستدعي sync، فالصف الجديد كان يُحذف بصمت عند الحفظ
    assert "$('addSize').onclick=()=>{addSize();sync()}" in TEMPLATE


def test_no_separate_positions_editor_is_left_behind():
    """قرار المستخدم (2026-09-30): التوزيع نفسه هو المواضع، فحُذف جدول المواضع.

    كل مفتاح هنا كان يربط زرًا أو سطرًا بعنصر لم يعد موجودًا، وهذا ما يجعل
    بقية السكربت تصمت بدل أن يعمل.
    """
    for gone in (
        'id="positionsBody"',
        'id="addPosition"',
        'function addPos',
        'function renderPositions',
        'function positionRows',
        "window.addPos=",
        '$(\'positionsBody\')',
        "addPos()",
    ):
        assert gone not in TEMPLATE, f"بقايا محرر المواضع في الصفحة: {gone}"
    assert "＋ إضافة صف" in TEMPLATE  # زر المقاسات ما زال
    assert "$('addPosition').onclick" not in TEMPLATE
    assert "addPos" not in NAV_SCRIPT
    assert 'data-tree-add="position"' not in TEMPLATE


def test_generated_positions_keep_saved_ids_and_descriptions():
    """الحذف مرفوض لموضع استُخدم في سجل حركات، فلا يجوز فقدان معرّفه."""
    assert "savedPositions=d.positions||d.master?.positions||[]" in TEMPLATE
    assert "id:match?match.id:null" in TEMPLATE
    assert "description:match?(match.description||''):''" in TEMPLATE
    assert "$('positionsJson').value=JSON.stringify(pos)" in TEMPLATE


def test_required_position_count_is_derived_and_readonly():
    """الخادم يرفض اختلاف العدد عن عدد المواضع، فالحقل يُحسب بدل كتابته يدويًا."""
    assert re.search(r'<input id="tirePositions"[^>]*readonly', TEMPLATE)
    assert "$('tirePositions').value=pos.length;" in TEMPLATE
    assert ".mdx .field input[readonly]" in STYLE


def test_differences_from_saved_positions_are_stated_before_saving():
    """لا إعادة توزيع صامتة: اختلاف الناتج عن المحفوظ يُعلَن قبل الحفظ."""
    assert "الإجمالي ${rows.length} موضع" in TEMPLATE
    assert "تختلف عن المواضع المحفوظة، فالحفظ سيعيد توزيعها" in TEMPLATE
    assert "layoutOverflow=total>MAX_PICKER_AXLES;" in TEMPLATE


def test_tires_section_is_reachable_from_the_editor():
    """العلّة التي وُوجهت: الأقسام الأخرى كانت مخفية بلا وسيلة العودة إليها."""
    assert "window.MATERIEL_MODEL_WORKSPACE_SECTIONS = sectionMap;" in NAV_SCRIPT
    assert "const idx=window.MATERIEL_MODEL_WORKSPACE_SECTIONS?.[section]" in TEMPLATE
    tabs = re.findall(r'data-model-workspace-tab="(\d)"', TEMPLATE)
    assert tabs == ["0", "1", "2", "3"]
    boxes = re.findall(r'data-workspace-section="(\w+)"', TEMPLATE)
    assert boxes == ["basic", "tires", "batteries", "specs"]
    assert ".mdx [data-model-workspace-tab].is-active" in STYLE