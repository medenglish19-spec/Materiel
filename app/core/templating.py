"""
core/templating.py
-----------------
كل وحدة تملك مجلد templates خاص بها، والقالب الأساسي المشترك موجود في
web/templates. جميع المسارات تُحوّل إلى مسارات مطلقة حتى لا يعتمد تشغيل
التطبيق على مجلد العمل الحالي (cwd).
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHARED_TEMPLATES_DIR = PROJECT_ROOT / "web" / "templates"


def get_module_templates(module_templates_dir: str) -> Jinja2Templates:
    module_dir = PROJECT_ROOT / module_templates_dir
    return Jinja2Templates(directory=[str(module_dir), str(SHARED_TEMPLATES_DIR)])
