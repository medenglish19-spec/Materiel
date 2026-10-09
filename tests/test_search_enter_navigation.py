"""Contract checks for the shared search and Enter-key behavior."""

from pathlib import Path


BASE_TEMPLATE = Path(__file__).resolve().parents[1] / "web" / "templates" / "base.html"


def test_shared_search_handles_search_inputs_and_get_forms() -> None:
    source = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert 'const searchSelector=\'input[type="search"],input.search-box' in source
    assert "const runSearch=()=>" in source
    assert "form.method.toLowerCase()==='get'" in source
    assert "form.requestSubmit()" in source
    assert "event.preventDefault();\n    search.click();" in source


def test_enter_navigation_moves_focus_and_validates_before_submit() -> None:
    source = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert "function installEnterNavigation()" in source
    assert "const next=controls[index+1]" in source
    assert "next.focus();return" in source
    assert "form.checkValidity()" in source
    assert "form.reportValidity()" in source
    assert "form.requestSubmit(next)" in source


def test_enter_navigation_preserves_native_editing_and_modifier_keys() -> None:
    source = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert "event.shiftKey||event.ctrlKey||event.metaKey||event.altKey" in source
    assert "event.isComposing" in source
    assert "current.closest('[contenteditable=\"true\"],textarea')" in source
    assert "current.hasAttribute('data-enter-native')" in source
    assert "current.type==='search'" in source
