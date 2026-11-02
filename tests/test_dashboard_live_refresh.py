from pathlib import Path


TEMPLATE = Path("app/modules/dashboard/templates/dashboard.html")


def test_dashboard_refreshes_its_existing_content_without_reloading_the_page():
    template = TEMPLATE.read_text(encoding="utf-8")

    assert 'data-dashboard-root' in template
    assert "setInterval(async function()" in template
    assert "document.visibilityState!=='visible'" in template
    assert "if(inFlight" in template
    assert "cache:'no-store'" in template
    assert "current.innerHTML=fresh.innerHTML" in template
    assert "location.reload" not in template
    assert "MaterielTables.refresh()" in template
