from datetime import date

from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.shared.mixins import AuditMixin


class Tire(Base, AuditMixin):
    __tablename__ = "tires"

    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String(80), unique=True, nullable=False, index=True)
    brand = Column(String(80), nullable=True)
    model = Column(String(80), nullable=True)
    size = Column(String(50), nullable=True)
    manufacture_date = Column(Date, nullable=True)
    receipt_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True, index=True)
    acquisition_document = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    movements = relationship("TireMovement", back_populates="tire", order_by="TireMovement.movement_date.desc(), TireMovement.id.desc()", cascade="all, delete-orphan")
    disposal = relationship("TireDisposal", back_populates="tire", uselist=False, cascade="all, delete-orphan")


class TirePosition(Base, AuditMixin):
    __tablename__ = "tire_positions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(250), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=True, index=True)
    axle_number = Column(Integer, nullable=True, index=True)
    side = Column(String(10), nullable=True)
    position_type = Column(String(20), nullable=True)

    movements = relationship("TireMovement", back_populates="position")


class TireModelSize(Base, AuditMixin):
    __tablename__ = "tire_model_sizes"

    id = Column(Integer, primary_key=True, index=True)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=False, index=True)
    size = Column(String(50), nullable=False)

    __table_args__ = (UniqueConstraint("equipment_model_id", "size", name="uq_tire_model_size"),)


class TireSystemSetting(Base, AuditMixin):
    __tablename__ = "tire_system_settings"

    id = Column(Integer, primary_key=True)
    validity_years = Column(Integer, nullable=False, default=3)


class TireDisposal(Base, AuditMixin):
    __tablename__ = "tire_disposals"

    id = Column(Integer, primary_key=True, index=True)
    tire_id = Column(Integer, ForeignKey("tires.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    disposal_date = Column(Date, nullable=False)
    disposal_document = Column(String(100), nullable=False)
    reason = Column(String(250), nullable=False)
    notes = Column(Text, nullable=True)

    tire = relationship("Tire", back_populates="disposal")


class TireMovement(Base, AuditMixin):
    __tablename__ = "tire_movements"

    id = Column(Integer, primary_key=True, index=True)
    tire_id = Column(Integer, ForeignKey("tires.id", ondelete="CASCADE"), nullable=False, index=True)
    movement_date = Column(Date, nullable=False, default=date.today, index=True)
    movement_type = Column(String(20), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True, index=True)
    position_id = Column(Integer, ForeignKey("tire_positions.id", ondelete="SET NULL"), nullable=True)
    meter_value = Column(Numeric(10, 1), nullable=True)
    document_number = Column(String(100), nullable=True)
    reason = Column(String(250), nullable=True)
    notes = Column(Text, nullable=True)

    tire = relationship("Tire", back_populates="movements")
    equipment = relationship("Equipment")
    position = relationship("TirePosition", back_populates="movements")
