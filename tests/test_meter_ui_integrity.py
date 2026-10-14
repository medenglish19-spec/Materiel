from pathlib import Path
import re
import shutil
import subprocess
import tempfile


TEMPLATE = Path(__file__).parents[1] / "app/modules/meter_readings/templates/meter_readings.html"
HISTORY_TEMPLATE = Path(__file__).parents[1] / "app/modules/meter_readings/templates/meter_readings_list.html"
BASE_TEMPLATE = Path(__file__).parents[1] / "web/templates/base.html"


def _scripts(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", text, flags=re.S | re.I)


def test_meter_readings_page_javascript_is_syntax_valid():
    scripts = _scripts(TEMPLATE)
    assert scripts, "صفحة قراءات العدادات يجب أن تحتوي على JavaScript"
    node = shutil.which("node")
    if not node:
        return
    for index, script in enumerate(scripts, start=1):
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            filename = handle.name
        try:
            result = subprocess.run([node, "--check", filename], text=True, capture_output=True)
        finally:
            Path(filename).unlink(missing_ok=True)
        assert result.returncode == 0, f"خطأ JavaScript في script #{index}: {result.stderr}"


def test_meter_readings_page_contains_script_and_core_client_handlers():
    scripts = _scripts(TEMPLATE)
    assert scripts, "صفحة قراءات العدادات يجب أن تحتوي على JavaScript"
    text = TEMPLATE.read_text(encoding="utf-8")
    script = "\n".join(scripts)
    for marker in (
        "function openReadingModal()",
        "function openImportModal()",
        "function openDateModal()",
        "function openSelectedHistory()",
        "function toggleMoreFilters()",
        "function applyDateFilter()",
        "function clearDateFilter()",
        "function submitExcelImport()",
        "function printReadings()",
        "function exportPDF()",
        "function exportExcel()",
    ):
        assert marker in script, f"معالج JavaScript مفقود: {marker}"
    for removed_marker in (
        "function openPasteModal()",
        "function submitPastedReadings()",
        "raw.split(/\\r?\\n/)",
        "pasteData",
        "pasteModal",
        "bulk-create",
    ):
        assert removed_marker not in script and removed_marker not in text, f"خاصية اللصق ما زالت موجودة: {removed_marker}"


def test_meter_page_is_not_overridden_by_shared_base_meter_handlers():
    text = BASE_TEMPLATE.read_text(encoding="utf-8")
    assert "window.submitPastedReadings" not in text
    assert "oldForm.cloneNode(true)" not in text
    assert "getElementById('readingForm')" not in text


def test_meter_readings_page_keeps_all_core_actions():
    text = TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        "openReadingModal()",
        "openImportModal()",
        "openDateModal()",
        "openSelectedHistory()",
        "toggleMoreFilters()",
        "applyDateFilter()",
        "clearDateFilter()",
        "submitExcelImport()",
        "printReadings()",
        "exportPDF()",
        "exportExcel()",
        "meter-readings/import-excel",
        "/meter-readings/create",
    ):
        assert marker in text, f"وظيفة واجهة مفقودة: {marker}"
    for removed_marker in ("openPasteModal()", "submitPastedReadings()", "pasteModal", "pasteData", "meter-readings/bulk-create"):
        assert removed_marker not in text, f"مرجع قديم لخاصية اللصق ما زال موجودًا: {removed_marker}"


def test_meter_history_page_keeps_edit_delete_actions():
    text = HISTORY_TEMPLATE.read_text(encoding="utf-8")
    assert 'class="action-btn edit"' in text
    assert 'class="action-btn delete"' in text
    assert '<form id="editReadingForm" data-em-root>' in text
    assert "if(window.EditManager)EditManager.reset();" in text
    assert '/meter-readings/history/{{ equipment.id }}/update' in text
    assert '/meter-readings/history/{{ equipment.id }}/delete' in text
