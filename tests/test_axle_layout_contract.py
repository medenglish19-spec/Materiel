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
TREE_SCRIPT = (ROOT / "static/js/master-data-tree.js").read_text(encoding="utf-8")
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
    assert 'id="addPosition"' in tires_box


def test_axle_wheel_picker_offers_exactly_single_and_dual():
    assert _count_axle_wheel_radios(TEMPLATE) == {"single", "dual"}
    # القاعدة نفسها في جافاسكربت (single = نوع واحد، dual = داخلي ثم خارجي)
    assert "const WHEEL_CHOICE_TYPES={single:['single'],dual:['inner','outer']};" in TEMPLATE
    assert "const AXLE_SIDE_ORDER=['right','left'];" in TEMPLATE


def test_positions_are_generated_automatically_on_any_change():
    # تغيير الاختيار يولّد، وعدد المحاور يولّد، والجدول اليدوي يبقى موجودًا
    assert "r.addEventListener('change',applyAxleLayout)" in TEMPLATE
    assert "$('axleCount').addEventListener('input'" in TEMPLATE
    assert 'id="addPosition"' in TEMPLATE
    assert 'id="addSize"' in TEMPLATE
    # زر «＋ إضافة صف» لم يكن يستدعي sync، فالصف الجديد كان يُحذف بصمت عند الحفظ
    assert "$('addPosition').onclick=()=>{addPos();sync()}" in TEMPLATE
    assert "$('addSize').onclick=()=>{addSize();sync()}" in TEMPLATE


def test_required_position_count_is_derived_and_readonly():
    """الخادم يرفض اختلاف العدد عن عدد الصفوف، فالحقل يُحسب بدل كتابته يدويًا."""
    assert re.search(r'<input id="tirePositions"[^>]*readonly', TEMPLATE)
    assert "$('tirePositions').value=pos.length;" in TEMPLATE
    assert ".mdx .field input[readonly]" in STYLE


def test_manual_changes_are_not_hidden_from_the_user():
    """لا تناقض صامت: إن اختلفت الصفوف عن التوزيع يظهر أنها يدوية."""
    assert "updatePositionsSummary" in TEMPLATE
    assert "مولّدة من التوزيع:" in TEMPLATE
    assert "معدّلة يدويًا:" in TEMPLATE


def test_tires_section_is_reachable_from_the_editor():
    """العلّة التي وُوجهت: الأقسام الأخرى كانت مخفية بلا وسيلة العودة إليها."""
    assert "window.MATERIEL_MODEL_WORKSPACE_SECTIONS = sectionMap;" in TREE_SCRIPT
    assert "const idx=window.MATERIEL_MODEL_WORKSPACE_SECTIONS?.[section]" in TEMPLATE
    tabs = re.findall(r'data-model-workspace-tab="(\d)"', TEMPLATE)
    assert tabs == ["0", "1", "2", "3"]
    boxes = re.findall(r'data-workspace-section="(\w+)"', TEMPLATE)
    assert boxes == ["basic", "tires", "batteries", "specs"]
    assert ".mdx [data-model-workspace-tab].is-active" in STYLE