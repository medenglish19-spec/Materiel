"""تفرّد رقم طلب الغيار: رقم واحد لا يتكرر.

الرقم فريد تماماً: لا يمكن إنشاء طلبين بنفس الرقم، ولا人可以 أن يأخذ
رقمَ طلبٍ آخر عند التعديل، بينما التعديل على الطلب يبقى بلا رقمه.

القاعدة مطبَّقة على مستويين: فحصٌ في الخدمة قبل الحفظ، وقيد `UNIQUE` في
القاعدة يرفض أي تجاوز. الاختبارات هنا تمشي على الـ endpoints الفعلية،
وتفحص القيد نفسه في القاعدة مباشرةً لتتأكد أن لا طبقة تُسقطه.
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database import session as session_module
from app.database.base import Base
from app.modules.spare_parts_requests import services
from app.modules.spare_parts_requests.models import SparePartRequest
from web import main

ROOT = Path(__file__).resolve().parents[1]

USERNAME = "request-number-keeper"
PASSWORD = "Test@12345"
TAKEN = "رقم الطلب مستخدم مسبقًا، يرجى إدخال رقم آخر."

DAY_ONE = date(2026, 4, 1)
DAY_TWO = date(2026, 4, 2)


@pytest.fixture(scope="module")
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    db = TestingSession()
    try:
        base = _seed(db)
    finally:
        db.close()

    def new_fault(day=DAY_ONE):
        """عطل جديد: العطل يقبل طلب غيار واحداً، فيحتاج كل اختبار عطلاً."""
        session = TestingSession()
        try:
            return _new_fault(session, base, day)
        finally:
            session.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)
        patch.setattr(session_module, "SessionLocal", TestingSession)

        app = main.create_app()
        app.dependency_overrides[session_module.get_db] = override_get_db

        with TestClient(app) as c:
            response = c.post(
                "/login",
                data={"username": USERNAME, "password": PASSWORD},
                follow_redirects=False,
            )
            assert response.status_code in (302, 303), "فشل تسجيل الدخول"
            yield c, new_fault


def _seed(db):
    """مستخدم واحد وعتاد واحد: كل عطل يُبنى عليهما."""
    from app.core.security import hash_password
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentType
    from app.modules.users.models import User

    user = User(
        username=USERNAME,
        full_name="أمين الأرقام",
        hashed_password=hash_password(PASSWORD),
        role="admin",
    )
    db.add(user)
    db.flush()

    eq_type = EquipmentType(name="حافلات", measurement_unit="km")
    db.add(eq_type)
    db.flush()
    equipment = Equipment(
        asset_code="NB-1",
        registration_number="444-TEST",
        equipment_type_id=eq_type.id,
        technical_condition="ready",
        operational_status="available",
    )
    db.add(equipment)
    db.flush()
    db.commit()

    return {"user": user.id, "equipment": equipment.id}


def _new_fault(db, base, day):
    from app.modules.faults_repairs.models import Fault

    fault = Fault(
        equipment_id=base["equipment"],
        reported_date=day,
        fault_type="تعطل",
        description="وصف",
        severity="high",
        status="open",
        exploitation_impact="limited",
        created_by_id=base["user"],
    )
    db.add(fault)
    db.commit()
    return fault.id


def _create(client, fault_id, number, day):
    return client.post(
        "/api/spare-parts-requests",
        json={
            "request_number": number,
            "request_date": day.isoformat(),
            "source_type": "fault",
            "source_id": fault_id,
            "items": [{"part_name": "قطعة " + number, "requested_quantity": 1}],
        },
    )


# ------------------------------------------- ١) رقم جديد يُقبل، ٢) مكرر يُرفض


class TestCreateRequestNumber:
    def test_a_new_number_is_accepted(self, client):
        page, new_fault = client

        response = _create(page, new_fault(DAY_ONE), "NB-900", DAY_ONE)

        assert response.status_code == 201, response.text
        assert response.json()["request_number"] == "NB-900"

    def test_the_same_number_is_refused(self, client):
        page, new_fault = client
        _create(page, new_fault(DAY_ONE), "NB-901", DAY_ONE)

        response = _create(page, new_fault(DAY_TWO), "NB-901", DAY_TWO)

        assert response.status_code == 400, response.text
        assert response.text == '{"detail":"' + TAKEN + '"}'

    def test_the_message_names_the_number_and_asks_for_another(self, client):
        """الرسالة تشرح للمستخدم ما يفعله، لا «UNIQUE constraint failed»."""
        page, new_fault = client
        _create(page, new_fault(DAY_ONE), "NB-902", DAY_ONE)

        response = _create(page, new_fault(DAY_TWO), "NB-902", DAY_TWO)

        assert "رقم الطلب مستخدم مسبقًا" in response.text
        assert "يرجى إدخال رقم آخر" in response.text
        assert "UNIQUE" not in response.text
        assert "IntegrityError" not in response.text

    def test_the_refused_duplicate_is_not_stored(self, client):
        page, new_fault = client
        _create(page, new_fault(DAY_ONE), "NB-903", DAY_ONE)

        _create(page, new_fault(DAY_TWO), "NB-903", DAY_TWO)

        listed = page.get("/api/spare-parts-requests").json()
        assert [r["request_number"] for r in listed].count("NB-903") == 1

    def test_the_second_fault_stays_free_after_a_refusal(self, client):
        """الرفض يسبق أي حفظ، فلا يستهلك العطلُ الطلبَ الفاشل."""
        page, new_fault = client
        _create(page, new_fault(DAY_ONE), "NB-904", DAY_ONE)
        spare = new_fault(DAY_TWO)

        _create(page, spare, "NB-904", DAY_TWO)

        response = _create(page, spare, "NB-905", DAY_TWO)
        assert response.status_code == 201, response.text


# --------------------------------- ٣) تعديل يبقي برقمه، ٤) لا يأخذ رقمَ طلبٍ آخر


class TestUpdateRequestNumber:
    def test_keeping_the_same_number_is_accepted(self, client):
        page, new_fault = client
        created = _create(page, new_fault(DAY_ONE), "NB-906", DAY_ONE).json()

        response = page.patch(
            f"/api/spare-parts-requests/{created['id']}",
            json={"request_number": "NB-906", "notes": "ملاحظة بعد التعديل"},
        )

        assert response.status_code == 200, response.text
        reread = page.get(f"/api/spare-parts-requests/{created['id']}").json()
        assert reread["request_number"] == "NB-906"
        assert reread["notes"] == "ملاحظة بعد التعديل"

    def test_taking_another_requests_number_is_refused(self, client):
        page, new_fault = client
        first = _create(page, new_fault(DAY_ONE), "NB-907", DAY_ONE).json()
        _create(page, new_fault(DAY_TWO), "NB-908", DAY_TWO)

        response = page.patch(
            f"/api/spare-parts-requests/{first['id']}",
            json={"request_number": "NB-908"},
        )

        assert response.status_code == 400, response.text
        assert response.text == '{"detail":"' + TAKEN + '"}'

    def test_the_refused_rename_keeps_the_old_number(self, client):
        page, new_fault = client
        first = _create(page, new_fault(DAY_ONE), "NB-909", DAY_ONE).json()
        _create(page, new_fault(DAY_TWO), "NB-910", DAY_TWO)

        page.patch(
            f"/api/spare-parts-requests/{first['id']}",
            json={"request_number": "NB-910"},
        )

        reread = page.get(f"/api/spare-parts-requests/{first['id']}").json()
        assert reread["request_number"] == "NB-909"

    def test_an_untouched_number_is_left_alone(self, client):
        """تعديل حقل آخر لا يفحص الرقم ولا يغيّره."""
        page, new_fault = client
        created = _create(page, new_fault(DAY_ONE), "NB-911", DAY_ONE).json()

        response = page.patch(
            f"/api/spare-parts-requests/{created['id']}",
            json={"notes": "بدون رقم"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["request_number"] == "NB-911"


# ------------------------------- نصٌّ حرّ: أرقام ورموز وحروف، بلا إعادة صياغة


class TestNumberIsFreeText:
    def test_letters_digits_and_symbols_are_kept_as_typed(self, client):
        """رقم كـ«70001/26» أو«NB-1-A» يُحفظ كما هو، بلا تغيير ولا ترتيب."""
        page, new_fault = client

        response = _create(page, new_fault(DAY_ONE), "70001/26-أ.ب", DAY_ONE)

        assert response.status_code == 201, response.text
        assert response.json()["request_number"] == "70001/26-أ.ب"

    def test_surrounding_spaces_do_not_open_a_second_number(self, client):
        """« NB-920 » و«NB-920» رقم واحد، لا رقمان مختلفان."""
        page, new_fault = client
        first = _create(page, new_fault(DAY_ONE), "  NB-920  ", DAY_ONE)
        assert first.status_code == 201, first.text
        assert first.json()["request_number"] == "NB-920", "المسافات الطرفية جزء من الرقم؟"

        response = _create(page, new_fault(DAY_TWO), "NB-920", DAY_TWO)

        assert response.status_code == 400, response.text
        assert response.text == '{"detail":"' + TAKEN + '"}'

    def test_editing_keeps_its_own_number_despite_stray_spaces(self, client):
        """طلب يبعث رقمه بمسافة طرفية يبقى على رقمه، لا يُرفَض خطأً."""
        page, new_fault = client
        created = _create(page, new_fault(DAY_ONE), "NB-921", DAY_ONE).json()

        response = page.patch(
            f"/api/spare-parts-requests/{created['id']}",
            json={"request_number": " NB-921 "},
        )

        assert response.status_code == 200, response.text
        assert response.json()["request_number"] == "NB-921"

    def test_a_blank_number_is_refused(self, client):
        """رقم من مسافات ليس رقماً، ولا رقمان منه يتفرّدان بلا معنى."""
        page, new_fault = client

        response = _create(page, new_fault(DAY_ONE), "   ", DAY_ONE)

        assert response.status_code == 400, response.text
        assert "رقم الطلب مطلوب" in response.text

    def test_letter_case_makes_a_different_number(self, client):
        """«nb-922» و«NB-922» رقمان مختلفان: المقارنة حرفية كما في القاعدة."""
        page, new_fault = client
        assert _create(page, new_fault(DAY_ONE), "nb-922", DAY_ONE).status_code == 201

        response = _create(page, new_fault(DAY_TWO), "NB-922", DAY_TWO)

        assert response.status_code == 201, response.text

    def test_the_comparison_is_exact_on_both_sides(self):
        """القاعدة تقارن بالنص كما هو، فلا يختلف قولها عن قول الفحص."""
        column = SparePartRequest.__table__.c.request_number
        assert column.type.python_type is str
        assert column.unique is True


# --------------------------------------- القيد نفسه في القاعدة وشبكة الأمان


class TestDatabaseConstraint:
    def test_the_column_is_unique_in_the_database(self):
        """القيد في القاعدة نفسها، لا في الفحص البرمجي وحده."""
        column = SparePartRequest.__table__.c.request_number
        assert column.unique is True, "العمود غير معلَّم unique في النموذج"

    def test_the_database_refuses_a_duplicate_row(self):
        """قيد `uq_spare_part_request_number` يرفض الصفّ المكرر من lado القاعدة."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSession = sessionmaker(bind=engine, autoflush=False)
        Base.metadata.create_all(engine)
        db = TestingSession()
        try:
            first = SparePartRequest(
                request_number="DB-1", request_date=DAY_ONE,
                source_type="fault", fault_id=1,
            )
            db.add(first)
            db.commit()
            db.add(
                SparePartRequest(
                    request_number="DB-1", request_date=DAY_TWO,
                    source_type="fault", fault_id=1,
                )
            )
            with pytest.raises(IntegrityError) as caught:
                db.commit()
            assert "request_number" in str(caught.value)
        finally:
            db.rollback()
            db.close()

    def test_a_race_still_yields_the_friendly_message(self, client):
        """لو مرّ الطلبان معاً من الفحص، فالقيد يصدّ الثاني بلطف لا بخطأ SQL."""
        page, new_fault = client
        _create(page, new_fault(DAY_ONE), "NB-912", DAY_ONE)
        original = services._check_request_number_free

        def blinded(db, request_number, exclude_id=None):
            return None  # محاكاة سباق: الفحص المسبق لا يرى التكرار

        services._check_request_number_free = blinded
        try:
            response = _create(page, new_fault(DAY_TWO), "NB-912", DAY_TWO)
        finally:
            services._check_request_number_free = original

        assert response.status_code == 400, response.text
        assert response.text == '{"detail":"' + TAKEN + '"}'

    def test_the_session_survives_a_refused_duplicate(self, client):
        """الرفض يتراجع عن الجلسة، فالطلب التالي لا يفشل على جلسة مكسورة."""
        page, new_fault = client
        _create(page, new_fault(DAY_ONE), "NB-913", DAY_ONE)
        spare = new_fault(DAY_TWO)

        _create(page, spare, "NB-913", DAY_TWO)

        response = _create(page, spare, "NB-914", DAY_TWO)
        assert response.status_code == 201, response.text
