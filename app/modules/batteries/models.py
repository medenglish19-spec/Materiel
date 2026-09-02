from datetime import date

from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text
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
