from datetime import date, timedelta
from pathlib import Path

from app.modules.missions.models import Mission
from app.modules.missions.services import mission_status


def test_mission_status_is_date_derived():
    today = date.today()
    assert mission_status(Mission(start_date=today + timedelta(days=1))) == "planned"
    assert mission_status(Mission(start_date=today)) == "running"
    assert mission_status(Mission(start_date=today - timedelta(days=2), end_date=today)) == "running"


def test_mission_page_dialogs_and_driver_actions_are_in_their_own_pages():
    page = Path("app/modules/missions/templates/missions.html").read_text(encoding="utf-8")
    base = Path("web/templates/base.html").read_text(encoding="utf-8")
    drivers_page = Path("app/modules/missions/templates/drivers.html").read_text(encoding="utf-8")
    records_page = Path("app/modules/missions/templates/mission_records.html").read_text(encoding="utf-8")

    assert 'id="openMissionDialog"' in page
    assert '<dialog class="mission-dialog" id="missionDialog"' in page
    mission_dialog_start = page.index('<dialog class="mission-dialog" id="missionDialog"')
    mission_form_start = page.index('<form method="post" action="/missions"')
    assert mission_dialog_start < mission_form_start < page.index("</dialog>", mission_dialog_start)
    assert "missionDialog.showModal()" in page
    assert "id=\"closeMissionDialog\"" in page
    assert "mission-fixed-add-driver" not in page
    assert "nav.insertBefore(addDriver" not in page
    assert 'id="driverDialog"' not in page
    assert '<form method="post" action="/missions/drivers"' not in page
    # The overview link precedes these two management destinations in the shared nav.
    assert "['/missions/records','إدارة المهمات']" in base
    assert "['/missions/drivers','إدارة السائقين']" in base
    assert "سجل المهمات" not in page
    assert "لا توجد مهمات مسجلة." in records_page
    assert "<th>العتاد</th><th>رقم التسجيل</th><th>السائق</th>" in records_page
    assert "mission-total" in records_page and "<strong>{{ missions|length }}</strong>" in records_page
    assert 'href="/missions?open_mission=1"' in records_page
    assert "open_mission')==='1'" in page
    assert "searchParams.delete('open_mission')" in page
    assert "history.replaceState" in page
    assert "MATERIEL · MISSIONS" not in records_page
    assert "عرض المهمات المسجلة ومعلومات العتاد والسائق والوجهة." not in records_page
    assert "العودة إلى لوحة المهمات" not in records_page
    assert '<a class="mission-drivers-link" href="/missions/drivers">إدارة السائقين</a>' not in page
    assert '<section class="mission-overview"' in page
    assert "mission-metric" in page and "mission-overview>div" in page
    assert "مخططة</span><b>{{ counts.planned }}" in page
    assert "تنتهي خلال 30 يومًا" in page and "license_expiry_alerts.expired|length" in page
    assert page.count('data-mission-detail=') == 5
    assert 'data-detail-panel="{{ status }}" hidden' in page
    assert '("planned", "مخططة")' in page
    assert '("running", "جارية")' in page
    assert '("completed", "منتهية")' in page
    assert '("expired", "منتهية"' in page
    assert '("expiring", "تنتهي خلال 30 يومًا"' in page
    assert "لا توجد مهمات {{ label }}." in page
    assert "لا توجد رخص {{ label }}." in page
    assert "تنبيهات صلاحية الرخص" not in drivers_page
    assert 'id="driverDialog"' in drivers_page
    assert "＋ إضافة سائق" in drivers_page
    assert 'class="drivers-list-actions"' in drivers_page
    assert drivers_page.index("<h2>قائمة السائقين</h2>") < drivers_page.index('id="openDriverDialog"')
    assert 'id="openDriverDialog"' in drivers_page
    assert "open.addEventListener('click'" in drivers_page
    assert 'id="openUnassignedEquipment"' in drivers_page
    assert '({{ unassigned_equipment|length }})' in drivers_page
    assert 'id="unassignedEquipmentDialog"' in drivers_page
    assert '<th>العتاد</th><th>رقم التسجيل</th><th>النوع</th><th>الطراز</th>' in drivers_page
    assert '<th>رمز العتاد</th>' not in drivers_page
    assert 'data-add-driver-for="{{ item.id }}"' in drivers_page
    assert "equipmentSelect.value=addButton.getAttribute('data-add-driver-for')" in drivers_page
    assert "nav.insertBefore(addDriver,missionsLink.nextSibling)" not in drivers_page
    assert '<a href="/missions">المهمات</a>' not in drivers_page
