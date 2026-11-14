from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, Numeric
from app.database.base import Base


def utc_now():
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class MeterReadingOperation(Base):
    __tablename__ = "meter_reading_operations"
    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(30), nullable=False)
    filename = Column(String(255), nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    status = Column(String(30), nullable=False, default="draft")
    total_rows = Column(Integer, nullable=False, default=0)
    accepted_rows = Column(Integer, nullable=False, default=0)
    rejected_rows = Column(Integer, nullable=False, default=0)
    reading_ids = Column(JSON, nullable=False, default=list)
    rolled_back_at = Column(DateTime, nullable=True)
    rolled_back_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class MeterReadingOperationEvent(Base):
    __tablename__ = "meter_reading_operation_events"
    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(Integer, ForeignKey("meter_reading_operations.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    details = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)


class MeterReadingChange(Base):
    """A log row describing a meter-data change, separate from the reading itself."""
    __tablename__ = "meter_reading_changes"
    id = Column(Integer, primary_key=True, index=True)
    reading_id = Column(Integer, ForeignKey("meter_readings.id", ondelete="SET NULL"), nullable=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True)
    operation_id = Column(Integer, ForeignKey("meter_reading_operations.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    changed_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    action = Column(String(30), nullable=False, default="update")
    source = Column(String(30), nullable=False, default="manual")
    reading_date = Column(DateTime, nullable=True)
    unit = Column(String(20), nullable=False, default="hours")
    old_value = Column(Numeric(10, 1), nullable=True)
    new_value = Column(Numeric(10, 1), nullable=True)
    details = Column(Text, nullable=True)
