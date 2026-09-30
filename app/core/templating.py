"""
core/templating.py
-----------------
كل وحدة تملك مجلد templates خاص بها، والقالب الأساسي المشترك موجود في
web/templates. جميع المسارات تُحوّل إلى مسارات مطلقة حتى لا يعتمد تشغيل
التطبيق على مجلد العمل الحالي (cwd).
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.labels import LABELS, label, label_options


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"


def get_module_templates(module_templates_dir: str) -> Jinja2Templates:
    """بيئة Jinja الخاصة بالوحدة، مع تسميات عربية مشتركة.

    كل وحدة تبني بيئتها هنا، فهذه هي النقطة الوحيدة التي تحقن
    `label()` / `label_options()` / `LABELS` في كل القوالب، وتصلح
    أيضاً لـJavaScript عبر `{{ LABELS | tojson }}`.
    """
    module_dir = PROJECT_ROOT / module_templates_dir
    templates = Jinja2Templates(directory=[str(module_dir), str(SHARED_TEMPLATES_DIR)])
    templates.env.globals.update(label=label, label_options=label_options, LABELS=LABELS)
    return templates
