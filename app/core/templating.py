"""
core/templating.py
-----------------
كل وحدة تملك مجلد templates خاص بها، والقالب الأساسي المشترك موجود في
web/templates. جميع المسارات تُحوّل إلى مسارات مطلقة حتى لا يعتمد تشغيل
التطبيق على مجلد العمل الحالي (cwd).
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.branding import load_institution_name
from app.core.labels import LABELS, label, label_options


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"
PAGE_SECTIONS = {
    "dashboard": "لوحة التحكم",
    "equipment": "العتاد",
    "equipment-types": "أنواع العتاد",
    "maintenance": "الصيانة",
    "meter-readings": "العدادات",
    "faults-repairs": "الأعطال والإصلاحات",
    "spare-parts": "قطع الغيار",
    "spare-parts-distribution": "قطع الغيار",
    "spare-parts-history": "قطع الغيار",
    "spare-parts-received": "قطع الغيار",
    "spare-parts-return": "قطع الغيار",
    "spare-parts-requests": "قطع الغيار",
    "spare-parts-movements": "قطع الغيار",
    "tires": "الإطارات",
    "batteries": "البطاريات",
    "fuel": "الوقود",
    "missions": "المهمات",
    "users": "المستخدمون",
    "document-import": "استيراد المستندات",
    "equipment-maintenance": "صيانة العتاد",
}


def page_section(path: str) -> str:
    """Return the Arabic module label shown above each page title."""
    segments = path.strip("/").split("/")
    if len(segments) >= 3 and segments[0] == "equipment":
        equipment_subpages = {
            "batteries": "البطاريات",
            "fuel": "الوقود",
            "maintenance": "صيانة العتاد",
            "meters": "العدادات",
            "tires": "الإطارات",
        }
        if section := equipment_subpages.get(segments[2]):
            return section
    first_segment = segments[0]
    return PAGE_SECTIONS.get(first_segment, "الرئيسية")


def get_module_templates(module_templates_dir: str) -> Jinja2Templates:
    """بيئة Jinja الخاصة بالوحدة، مع تسميات عربية مشتركة.

    كل وحدة تبني بيئتها هنا، فهذه هي النقطة الوحيدة التي تحقن
    `label()` / `label_options()` / `LABELS` في كل القوالب، وتصلح
    أيضاً لـJavaScript عبر `{{ LABELS | tojson }}`.
    """
    module_dir = PROJECT_ROOT / module_templates_dir
    templates = Jinja2Templates(directory=[str(module_dir), str(SHARED_TEMPLATES_DIR)])
    templates.env.globals.update(
        label=label,
        label_options=label_options,
        LABELS=LABELS,
        institution_name=load_institution_name,
        page_section=page_section,
    )
    return templates
