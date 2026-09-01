from datetime import date

from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.shared.mixins import AuditMixin


class FuelRecord(Base, AuditMixin):
    __tablename__ = "fuel_records"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    fueling_date = Column(Date, nullable=False, default=date.today, index=True)
    sequence_number = Column(Integer, nullable=False)
    meter_value = Column(Numeric(10, 1), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)
    fuel_type = Column(String(40), nullable=True)
    document_number = Column(String(100), nullable=True)
    station = Column(String(120), nullable=True)
    notes = Column(Text, nullable=True)
    equipment = relationship("Equipment")
