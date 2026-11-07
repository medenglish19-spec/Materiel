from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (register models for create_all)
from app.database.base import Base
from app.modules.faults_repairs import services
from app.modules.faults_repairs.models import Fault, Repair, RepairPart, SparePart
from app.modules.faults_repairs.schemas import (
    RepairPartCreate,
    SparePartCreate,
    SparePartUpdate,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _seed_repair(db):
    fault = Fault(
        equipment_id=1,
        reported_date=date(2026, 1, 1),
        description="اختبار",
        severity="low",
        fault_type="QA",
        exploitation_impact="limited",
    )
    db.add(fault)
    db.flush()
    repair = Repair(fault_id=fault.id, repair_date=date(2026, 1, 2), action_taken="اختبار")
    db.add(repair)
    db.commit()
    return repair


def test_create_spare_part_rejects_duplicate_number(db):
    services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-1", name="قطعة", receiving_document="QA-DOC"))

    with pytest.raises(ValueError, match="رقم القطعة مستخدم مسبقًا"):
        services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-1", name="قطعة أخرى", receiving_document="QA-DOC"))

    assert db.query(SparePart).filter(SparePart.part_number == "QA-DUP-1").count() == 1


def test_update_spare_part_rejects_duplicate_number(db):
    first = services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-2", name="قطعة", receiving_document="QA-DOC"))
    second = services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-3", name="قطعة", receiving_document="QA-DOC"))

    with pytest.raises(ValueError, match="رقم القطعة مستخدم مسبقًا"):
        services.update_spare_part(db, second, SparePartUpdate(part_number="QA-DUP-2"))

    db.refresh(second)
    assert second.part_number == "QA-DUP-3"
    assert first.part_number == "QA-DUP-2"


def test_add_repair_part_rejects_duplicate_line(db):
    repair = _seed_repair(db)
    part = services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-4", name="قطعة", receiving_document="QA-DOC"))
    payload = RepairPartCreate(
        repair_id=repair.id,
        spare_part_id=part.id,
        quantity=1,
        distribution_document="QA-DOC",
    )
    services.add_repair_part(db, payload)

    with pytest.raises(ValueError, match="مضافة مسبقًا"):
        services.add_repair_part(db, payload)

    assert db.query(RepairPart).filter(
        RepairPart.repair_id == repair.id,
        RepairPart.spare_part_id == part.id,
    ).count() == 1


def test_create_spare_part_translates_unique_race_to_value_error(db, monkeypatch):
    def racing_commit():
        raise IntegrityError(
            "INSERT INTO spare_parts",
            {},
            Exception("UNIQUE constraint failed: spare_parts.part_number"),
        )

    monkeypatch.setattr(db, "commit", racing_commit)
    with pytest.raises(ValueError, match="رقم القطعة مستخدم مسبقًا"):
        services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-5", name="قطعة", receiving_document="QA-DOC"))


def test_create_spare_part_does_not_hide_unrelated_integrity_errors(db, monkeypatch):
    def failing_commit():
        raise IntegrityError(
            "INSERT INTO spare_parts",
            {},
            Exception("NOT NULL constraint failed: spare_parts.name"),
        )

    monkeypatch.setattr(db, "commit", failing_commit)
    with pytest.raises(IntegrityError):
        services.create_spare_part(db, SparePartCreate(part_number="QA-DUP-6", name="قطعة", receiving_document="QA-DOC"))
