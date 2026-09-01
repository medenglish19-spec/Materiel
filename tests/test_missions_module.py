from datetime import date, timedelta

from app.modules.missions.models import Mission
from app.modules.missions.services import mission_status


def test_mission_status_is_date_derived():
    today = date.today()
    assert mission_status(Mission(start_date=today + timedelta(days=1))) == "planned"
    assert mission_status(Mission(start_date=today)) == "running"
    assert mission_status(Mission(start_date=today - timedelta(days=2), end_date=today)) == "completed"
