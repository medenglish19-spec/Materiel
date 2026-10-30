"""Source-contract checks for the shared per-column filters.

These assertions pin the wiring that the pure core cannot cover in Node: the
script is loaded before the shared table engine, the engine ships the expected
skip rules and refresh API, the styles hide rows with a class (so they compose
with each page's own search/pagination), and the maintenance operation library
— which ships its own filters — is left untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "web" / "templates" / "base.html"
ENGINE = ROOT / "static" / "js" / "mt-tables.js"
CORE = ROOT / "static" / "js" / "mt-filters-core.js"
CSS = ROOT / "static" / "css" / "mt-tables.css"
LIBRARY = ROOT / "app" / "modules" / "maintenance" / "templates" / "maintenance_rules_model_only.html"


def _base() -> str:
    return BASE.read_text(encoding="utf-8")


def _engine() -> str:
    return ENGINE.read_text(encoding="utf-8")


def _css() -> str:
    return CSS.read_text(encoding="utf-8")


# --------------------------------------------------------------- load order

def test_filter_core_is_loaded_before_the_shared_table_engine():
    base = _base()
    assert 'src="/static/js/mt-filters-core.js"' in base
    core_at = base.index("/static/js/mt-filters-core.js")
    tables_at = base.index("/static/js/mt-tables.js")
    assert core_at < tables_at, "يجب تحميل نواة التصفية قبل محرك الجداول"
    assert "?v=maintenance-record-filters" in base


def test_core_and_engine_exist_as_tracked_static_assets():
    assert CORE.exists()
    assert ENGINE.exists()


# ------------------------------------------------- engine contract (markers)

def test_engine_enhances_region_tables_automatically():
    source = _engine()
    assert "var CORE = window.MaterielFilterCore;" in source
    assert "document.querySelectorAll('[data-mt-region]')" in source
    assert "function enhanceTable(table)" in source
    assert "function unenhanceTable(table)" in source


def test_table_region_height_tracks_page_scroll():
    source = _engine()
    assert "window.addEventListener('scroll', scheduleFit" in source
    assert "window.innerHeight - Math.max(0, rect.top) - GAP" in source
    assert "region.style.removeProperty('--mt-region-max-height')" in source


def test_engine_uses_the_shared_core_matching_api():
    source = _engine()
    assert "CORE.isFilterActive(" in source
    assert "CORE.matchesCell(" in source
    assert "detectKind(" in source
    assert "new Set(" in source


def test_engine_hides_rows_with_a_class_so_search_and_filters_compose():
    source = _engine()
    assert "row.classList.toggle('mt-col-hidden', !ok)" in source
    assert "classList.remove('mt-col-hidden')" in source
    # Never clamp a row's inline display — the page's own search owns that.
    assert "style.display" not in source


def test_engine_skips_action_editor_hierarchical_and_self_filtered_tables():
    source = _engine()
    assert "table.querySelector('.col-filter')" in source
    assert "function isEditorTable(table)" in source
    assert 'tbody input:not([type="checkbox"]):not([type="radio"]), tbody select, tbody textarea' in source
    assert "function isHierarchicalTable(table)" in source
    assert "tbody tr[data-level]" in source
    assert "FILTER_SKIP_HEADERS" in source
    assert "looksLikeLinkColumn" in source
    assert "data-mt-filter-auxiliary" in source
    assert "mt:filters-applied" in source
    assert "data-mt-no-filter" in source


def test_engine_can_be_disabled_and_refreshed():
    source = _engine()
    assert "data-mt-filters-off" in source
    assert "data-mt-filters-ready" in source
    assert "refreshFilters: function () { enhanceAll(); }" in source
    assert "closeFilterMenu: closeFilterMenu" in source
    assert "MutationObserver" in source


def test_engine_injects_filter_buttons_only_on_the_client():
    source = _engine()
    assert "document.createElement('button')" in source
    assert "btn.className = 'mt-col-filter';" in source


# ----------------------------------------------------------- styles contract

def test_styles_hide_filtered_rows_in_all_eligible_tables():
    css = _css()
    assert "table tbody tr.mt-col-hidden{display:none!important}" in css
    assert ".mt-col-filter{" in css
    assert ".mt-filter-menu{" in css


def test_filter_menu_stays_right_to_left():
    assert "menu.setAttribute('dir', 'rtl')" in _engine()


# ------------------------------------------------- client-only enhancement

def test_no_template_ships_server_rendered_shared_filter_markup():
    """The buttons/menu are built in JS; templates never hard-code them."""
    offenders = []
    for path in (ROOT / "app").rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in ("mt-col-filter", "mt-filter-menu", "mt-col-hidden"):
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)}: {marker}")
    assert not offenders, offenders


# ------------------------------------------- maintenance library untouched

def test_maintenance_library_keeps_its_own_filter_implementation():
    template = LIBRARY.read_text(encoding="utf-8")
    # The library builds its rows through its own predicate …
    assert "state.operations.filter(op=>passesColumnFilters(op))" in template
    assert "function passesColumnFilters(op)" in template
    # … and ships its own trigger, which makes the shared engine skip it.
    assert 'class="col-filter"' in template
    assert "mt-col-filter" not in template
    assert "mt-filters-core.js" not in template


def test_maintenance_records_use_shared_filters_with_row_selection_and_action_menu():
    records = ROOT / "app" / "modules" / "maintenance" / "templates" / "maintenance_records.html"
    template = records.read_text(encoding="utf-8")
    assert 'data-mt-region' in template
    assert 'class="record-check"' in template
    assert 'class="record-operation-cell"' in template
    assert 'data-mt-filter-auxiliary' in template


def test_engine_recognises_the_library_self_filter_class():
    # The skip check and the library both use `.col-filter`; keep them aligned.
    assert ".col-filter" in _engine()
    assert "col-filter" in LIBRARY.read_text(encoding="utf-8")


def test_spare_parts_catalog_uses_shared_filters_in_its_single_header_row():
    catalog = ROOT / "app" / "modules" / "spare_parts_catalog" / "templates" / "catalog.html"
    template = catalog.read_text(encoding="utf-8")
    header = template.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert 'data-mt-region' in template
    assert header.count("<tr>") == 1
    assert 'class="mt-col-filter"' not in template
    assert all(f'data-mt-force-filter>{heading}</th>' in header for heading in ("الاسم", "الرمز التعريفي", "طراز العتاد", "الفئة", "الصورة", "الحالة / تعديل"))
    assert "data-mt-force-filter" in _engine()
    assert "if (!hasValue && !forceFilter) continue;" in _engine()


def test_other_read_only_tables_use_the_shared_filter_region():
    templates = {
        "maintenance_catalog_imports.html": ROOT / "app" / "modules" / "maintenance" / "templates" / "maintenance_catalog_imports.html",
        "maintenance_due.html": ROOT / "app" / "modules" / "maintenance" / "templates" / "maintenance_due.html",
        "maintenance_records.html": ROOT / "app" / "modules" / "maintenance" / "templates" / "maintenance_records.html",
        "repair_detail.html": ROOT / "app" / "modules" / "faults_repairs" / "templates" / "repair_detail.html",
        "equipment_list.html": ROOT / "app" / "modules" / "equipment" / "templates" / "equipment_list.html",
        "document_import_upload.html": ROOT / "app" / "modules" / "document_import" / "templates" / "upload.html",
        "drivers.html": ROOT / "app" / "modules" / "missions" / "templates" / "drivers.html",
    }
    for name, path in templates.items():
        source = path.read_text(encoding="utf-8")
        assert "data-mt-region" in source, f"{name} must wire its read-only tables to shared filters"

    equipment = templates["equipment_list.html"].read_text(encoding="utf-8")
    assert 'id="equipmentImportResults"' in equipment
    assert 'class="equipment-import-scroll mt-table-theme-green" data-mt-region' in equipment

    upload = templates["document_import_upload.html"].read_text(encoding="utf-8")
    assert '<div class="table-scroll mt-table-theme-green" data-mt-region><table class="tbl">' in upload
    assert '<table class="tbl">\n      <thead>\n        <tr>\n          <th>الاسم</th>' in upload  # editable preview stays outside shared filtering

    repair = templates["repair_detail.html"].read_text(encoding="utf-8")
    assert repair.count('class="rd-table-wrap mt-table-theme-green" data-mt-region') == 2

    drivers = templates["drivers.html"].read_text(encoding="utf-8")
    driver_table = drivers.split("قائمة السائقين", 1)[1]
    assert '<div class="table-wrap" data-mt-region>' in driver_table
    assert driver_table.count("data-mt-force-filter>") == 9
    assert '<th data-mt-no-filter>الإجراءات</th>' in driver_table


def test_standalone_meter_paste_preview_loads_shared_table_filters():
    page = (ROOT / "static" / "meter_readings_paste.html").read_text(encoding="utf-8")
    assert 'href="/static/css/mt-tables.css' in page
    assert 'src="/static/js/mt-filters-core.js"' in page
    assert 'src="/static/js/mt-tables.js' in page
    assert 'class="table-wrap mt-table-theme-green" data-mt-region><table>' in page


# ------------------------------------------------------ core module shape

def test_core_exports_the_documented_api():
    source = CORE.read_text(encoding="utf-8")
    for name in ("normalize", "parseNumber", "parseDate", "detectKind",
                 "matchesCell", "rowPasses", "isFilterActive"):
        assert re.search(rf"\b{name}:", source), name
    # UMD so Node can require it for the behavioural tests.
    assert "module.exports = api" in source
    assert "root.MaterielFilterCore = api" in source
