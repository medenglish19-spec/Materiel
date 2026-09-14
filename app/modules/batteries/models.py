from datetime import date

from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text, event
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.shared.mixins import AuditMixin


class Battery(Base, AuditMixin):
    __tablename__ = "batteries"
    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String(80), unique=True, nullable=False, index=True)
    brand = Column(String(80), nullable=True)
    model = Column(String(80), nullable=True)
    manufacture_date = Column(Date, nullable=True)
    receipt_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)
    acquisition_document = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    movements = relationship("BatteryMovement", back_populates="battery", order_by="BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()", cascade="all, delete-orphan")


class BatterySystemSetting(Base, AuditMixin):
    __tablename__ = "battery_system_settings"
    id = Column(Integer, primary_key=True)
    validity_years = Column(Integer, nullable=False, default=2)


class BatteryMovement(Base, AuditMixin):
    __tablename__ = "battery_movements"
    id = Column(Integer, primary_key=True, index=True)
    battery_id = Column(Integer, ForeignKey("batteries.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_date = Column(Date, nullable=False, default=date.today, index=True)
    movement_type = Column(String(20), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True)
    meter_value = Column(Numeric(10, 1), nullable=True)
    document_number = Column(String(100), nullable=True)
    reason = Column(String(250), nullable=True)
    notes = Column(Text, nullable=True)
    battery = relationship("Battery", back_populates="movements")
    equipment = relationship("Equipment")


@event.listens_for(BatteryMovement, "before_insert")
def _validate_battery_movement_policy(mapper, connection, target):
    if target.movement_type == "move":
        raise ValueError("نقل البطارية المباشر غير مسموح. يجب تسجيل الفك أولًا ثم التركيب.")
    if target.movement_type not in {"install", "remove"}:
        raise ValueError("نوع حركة البطارية غير صالح")
    if target.movement_type == "remove" and not (target.reason or "").strip():
        raise ValueError("سبب فك البطارية إلزامي")
