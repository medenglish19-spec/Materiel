"""عقود التسميات العربية الموحّدة (core/labels.py).

الهدف: ألّا يعود أي مفتاح إنجليزي إلى الواجهة العربية. لذلك يختبر الملف
أمرين:

1. **اكتمال التغطية** — كل قيمة معرَّفة في `schemas.py` (الوضعية، الحالة
   الفنية، حالة العطل، حالة التصليح) لها تسمية عربية. لو أُضيفت وضعية
   جديدة إلى `OPERATIONAL_STATUSES` ونُسيت تسميتها، يسقط الاختبار هنا لا في
   الإنتاج.
2. **عدم تكرار السلاسل** — القوالب تستخدم `label(...)` بدل `if/elif` خاص بها.
"""

import inspect
import re
from pathlib import Path

from app.core.labels import (
    FAULT_STATUS_LABELS,
    LABELS,
    OPERATIONAL_STATUS_LABELS,
    REPAIR_STATUS_LABELS,
    SEVERITY_LABELS,
    TECHNICAL_CONDITION_LABELS,
    label,
    label_options,
)
from app.core.templating import get_module_templates
from app.modules.equipment.schemas import OPERATIONAL_STATUSES, TECHNICAL_CONDITIONS
from app.modules.faults_repairs.schemas import FAULT_STATUSES, REPAIR_STATUSES

ROOT = Path(__file__).parents[1]


def _templates():
    return sorted(ROOT.glob("app/modules/*/templates/*.html")) + sorted(
        ROOT.glob("web/templates/*.html")
    )


# ------------------------------------------------------------------ اكتمال التغطية


def test_every_operational_status_has_a_label():
    assert OPERATIONAL_STATUSES == set(OPERATIONAL_STATUS_LABELS)


def test_every_technical_condition_has_a_label():
    assert TECHNICAL_CONDITIONS == set(TECHNICAL_CONDITION_LABELS)


def test_every_fault_status_has_a_label():
    assert FAULT_STATUSES == set(FAULT_STATUS_LABELS)


def test_every_repair_status_has_a_label():
    assert REPAIR_STATUSES == set(REPAIR_STATUS_LABELS)


def test_no_label_is_empty_or_still_english():
    for kind, mapping in LABELS.items():
        for key, text in mapping.items():
            assert text.strip(), f"{kind}.{key} تسمية فارغة"
            # المفتاح نفسه إنجليزي؛ التسمية يجب ألا تكون نسخة منه.
            assert text != key, f"{kind}.{key} تعرض المفتاح كما هو"
            assert not re.fullmatch(r"[A-Za-z_ ]+", text), f"{kind}.{key} غير مترجمة"


# --------------------------------------------------------------- سلوك الدالة


def test_label_translates_known_keys():
    assert label("operational", "in_maintenance") == "في الصيانة"
    assert label("technical", "broken") == "عاطل"
    assert label("fault", "waiting_parts") == "بانتظار قطع الغيار"
    assert label("repair", "completed") == "تم الإصلاح"
    assert label("severity", "critical") == "حرجة"


def test_label_falls_back_to_the_raw_value_instead_of_raising():
    """مفتاح جديد غير مترجم يجب أن يظهر كما هو، لا أن ينهار الصفحة."""
    assert label("operational", "brand_new_status") == "brand_new_status"
    assert label("unknown_kind", "whatever") == "whatever"
    assert label("operational", None) == ""
    assert label("operational", None, default="—") == "—"


def test_label_options_keep_display_order_and_shape():
    options = label_options("operational")
    assert options == list(OPERATIONAL_STATUS_LABELS.items())
    assert all(isinstance(value, str) and isinstance(text, str) for value, text in options)


# ---------------------------------------------------------------- حقن القوالب


def test_every_module_template_env_exposes_the_label_helpers():
    """نقطة الحقن الوحيدة هي get_module_templates؛ لو تعطّلت، سقطت كل القوالب."""
    templates = get_module_templates("app/modules/equipment/templates")

    assert templates.env.globals["label"] is label
    assert templates.env.globals["label_options"] is label_options
    assert templates.env.globals["LABELS"] is LABELS


def test_label_helpers_are_available_to_every_module():
    """13 وحدة كلها تمرّ من get_module_templates — لا بناء بيئة Jinja خارجها."""
    source = ROOT / "app" / "core" / "templating.py"
    assert "env.globals.update" in source.read_text(encoding="utf-8")


# ------------------------------------------------------- لا سلاسل if/elif متبقية


def test_templates_no_longer_duplicate_status_label_chains():
    """قوالب العتاد: لا if/elif يكرّر مفتاحين من الوضعية (كانت في 4 ملفات).

    استثناء مقصود: `equipment_meters.html` و`meter_readings_list.html`
    يعرضان سؤالاً مختلفاً — «هل يعمل؟» (نعم/لا) لا «أين هو؟»؛ لذلك يبقى
    عندهما فرع واحد على `unavailable` فقط.
    """
    offenders = []
    pattern = re.compile(r"\.operational_status\s*==")
    for template in _templates():
        text = template.read_text(encoding="utf-8")
        if len(pattern.findall(text)) >= 2:
            offenders.append(template.name)

    assert offenders == [], f"سلاسل وضعية مكرّرة باقية: {offenders}"


def test_working_state_stays_binary_where_it_is_a_different_question():
    """صفحتا العدّاد تجيبان «يعمل/لا يعمل» عمداً — لا تُوسَّع إلى خمس وضعيات."""
    for name in (
        "equipment/templates/equipment_meters.html",
        "meter_readings/templates/meter_readings_list.html",
    ):
        text = (ROOT / "app/modules" / name).read_text(encoding="utf-8")
        if name.endswith("meter_readings_list.html"):
            assert "حالة العداد" in text
            assert "status-success" in text and "status-danger" in text
        else:
            assert "لا يعمل" in text and "يعمل" in text, f"{name} فقد عرض حالة العمل"


def test_templates_no_longer_embed_inline_label_dictionaries():
    """القواميس المضمّنة ({"open":"مفتوح",...}) مكانها labels.py الآن."""
    offenders = []
    pattern = re.compile(r"\{\{\s*\{\s*\"(open|available|in_mission)\"\s*:")
    for template in _templates():
        text = template.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(template.name)

    assert offenders == [], f"قواميس تسميات مضمّنة باقية: {offenders}"


def test_operational_status_pages_use_the_shared_label():
    """الصفحات التي تعرض وضعية نصوصاً تستدعي `label`."""
    for name in (
        "dashboard/templates/dashboard.html",
        "equipment/templates/equipment_list.html",
        "equipment/templates/equipment_detail.html",
    ):
        text = (ROOT / "app" / "modules" / name).read_text(encoding="utf-8")
        assert "label('operational'" in text, f"{name} لا يستخدم التسمية الموحّدة"

    # صفحة التعداد العددي لا تعرض وضعية كنص (نِسَب فقط)، فلها خريطة في JS.
    for name in (
        "equipment/templates/equipment_list.html",
        "equipment/templates/equipment_numerical_status.html",
    ):
        text = (ROOT / "app" / "modules" / name).read_text(encoding="utf-8")
        assert "label_options('operational')" in text, f"{name} لا يولّد خيارات الفلترة"


def test_numerical_status_javascript_reads_the_injected_map():
    """الـJS لا يملك تسمياته الخاصة؛ يقرأ الخريطة المحقونة."""
    text = (ROOT / "app/modules/equipment/templates/equipment_numerical_status.html").read_text(
        encoding="utf-8"
    )

    assert "window.MATERIEL_LABELS = {{ LABELS | tojson }};" in text
    assert "const ops={available:" not in text, "الخريطة القديمة ما زالت مكتوبة يدوياً"
    assert "LAB.operational" in text and "LAB.technical" in text


def test_labels_module_stays_independent_from_domain_modules():
    """core لا يستورد modules: الاتجاه مقلوب عمداً (الاختبارات تغطي التطابق)."""
    import app.core.labels as labels_module

    source = inspect.getsource(labels_module)

    assert "from app.modules" not in source
    assert "import app.modules" not in source
