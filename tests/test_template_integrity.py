import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]


def test_all_html_templates_have_valid_jinja_syntax():
    template_dirs = [
        ROOT / "app",
        ROOT / "web",
    ]
    templates = []
    for base in template_dirs:
        templates.extend(base.rglob("templates/*.html"))
    assert templates, "No HTML templates were found"

    for path in templates:
        rel = path.relative_to(ROOT)
        env = Environment(
            loader=FileSystemLoader(str(path.parent)),
            undefined=StrictUndefined,
        )
        env.get_template(path.name)


def test_application_templates_use_shared_shell_except_login():
    templates = sorted((ROOT / "app").rglob("templates/*.html"))
    assert templates, "No application templates were found"

    for path in templates:
        text = path.read_text(encoding="utf-8")
        if path.as_posix().endswith("app/modules/users/templates/login.html"):
            continue
        assert '{% extends "base.html" %}' in text, f"Template bypasses shared shell: {path.relative_to(ROOT)}"
        assert not re.search(r"^\s*<!doctype\s+html\b", text, re.IGNORECASE | re.MULTILINE), f"Template contains a standalone document shell: {path.relative_to(ROOT)}"
        assert not re.search(r"^\s*<html\b", text, re.IGNORECASE | re.MULTILINE), f"Template contains a standalone html root: {path.relative_to(ROOT)}"
        assert not re.search(r"^\s*<body\b", text, re.IGNORECASE | re.MULTILINE), f"Template contains a standalone body root: {path.relative_to(ROOT)}"


def test_numerical_status_template_contains_required_labels():
    path = ROOT / "app/modules/equipment/templates/equipment_numerical_status.html"
    text = path.read_text(encoding="utf-8")
    for label in ("النظري", "المحقق", "الاحتياج", "الفائض", "عتاد خارج TED"):
        assert label in text
