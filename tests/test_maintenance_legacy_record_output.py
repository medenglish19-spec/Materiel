"""حارس: قراءة سجل صيانة بلا «عملية صيانة» لا تُسقط الـAPI.

الدفاع: MaintenanceRecordOut كان يرث مُتحقّق الإدخال الذي يشترط
operation_id، فأي صف قديم (operation_id = NULL) كان يُسقط
/api/maintenance/execution كاملةً بخطأ 500.

ملاحظة عن المعطيات: الإدراج محميّ الآن بمستمع في الموديل يمنع
السجل بلا عملية، لكن ذلك القيد أُضيف لاحقاً والعمود nullable، فتبقى
صفوف قديمة في القاعدة. لذلك تُدرَج في هذا الاختبار عبر SQL مباشراً
كما كانت تُكتب فعلاً، لا عبر ORM الذي يرفضها اليوم.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceRecord
from app.modules.maintenance.schemas import MaintenanceRecordCreate, MaintenanceRecordOut
from app.modules.users.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def _setup():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    eq_type = EquipmentType(name="نوع اختبار السجل القديم", measurement_unit="km")
    db.add(eq_type)
    db.flush()
    model = EquipmentModel(name="طراز اختبار السجل القديم", equipment_type_id=eq_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="LEGACY-REC-1",
        registration_number="سجل قديم",
        vin="LEGACYVIN1",
        equipment_type_id=eq_type.id,
        equipment_model_id=model.id,
    )
    db.add(equipment)
    db.commit()
    return db, equipment


def _insert_legacy_record(db, equipment_id):
    """صف قديم بلا عملية: يكتبه SQL مباشرة كما كانت القاعدة قبل القيد."""
    db.execute(
        text(
            "INSERT INTO maintenance_records "
            "(equipment_id, operation_id, plan_id, maintenance_date, "
            " reported_date, meter_value, status, is_scheduled, created_at) "
            "VALUES (:eid, NULL, NULL, :mdate, :rdate, :meter, 'completed', 0, :now)"
        ),
        {
            "eid": equipment_id,
            "mdate": "2024-03-01",
            "rdate": "2024-03-02",
            "meter": "100",
            "now": "2024-03-02 08:00:00",
        },
    )
    db.commit()


def test_output_schema_accepts_legacy_record_without_operation():
    db, equipment = _setup()
    try:
        _insert_legacy_record(db, equipment.id)
        record = db.query(MaintenanceRecord).one()

        out = MaintenanceRecordOut.model_validate(record)
        assert out.operation_id is None      # لا تُخترع عملية له
        assert out.plan_id is None
    finally:
        db.close()


def test_execution_endpoint_survives_a_legacy_record():
    """المسار الحقيقي: استجابة FastAPI كانت تُسقط كل القائمة بـ500."""
    import web.main as main

    db, equipment = _setup()
    try:
        _insert_legacy_record(db, equipment.id)

        def override_get_db():
            yield db

        admin = User(
            username="legacy-reader",
            full_name="قارئ اختبار السجل القديم",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        def override_user():
            return admin

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(main, "init_db", lambda: None)
            patch.setattr(main, "create_default_admin", lambda: None)
            patch.setattr(session_module, "SessionLocal", Session)

            app = main.create_app()
            app.dependency_overrides[session_module.get_db] = override_get_db
            app.dependency_overrides[get_current_user] = override_user

            with TestClient(app) as client:
                response = client.get("/api/maintenance/execution")

        assert response.status_code == 200, response.text[:400]
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["operation_id"] is None
    finally:
        db.close()


def test_input_still_requires_an_operation():
    """الحارس يبقى سارياً على الكتابة: لا نُضعف التحقق من الإدخال."""
    db, equipment = _setup()
    try:
        with pytest.raises(ValidationError) as exc:
            MaintenanceRecordCreate(
                equipment_id=equipment.id,
                operation_id=None,
                maintenance_date=date(2024, 3, 1),
            )
        assert "يجب تحديد عملية الصيانة" in str(exc.value)
    finally:
        db.close()