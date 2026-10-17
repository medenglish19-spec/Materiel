from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.shared.mixins import AuditMixin


class Mission(Base, AuditMixin):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_name = Column(String(120), nullable=True)
    mission_document = Column(String(100), nullable=True)
    purpose = Column(String(250), nullable=True)
    destination = Column(String(150), nullable=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    equipment = relationship("Equipment")

    @property
    def departure_meter(self):
        from app.modules.meter_readings.source_values import read_source_value
        return read_source_value(self, "departure_meter")

    @departure_meter.setter
    def departure_meter(self, value):
        from app.modules.meter_readings.source_values import write_source_value
        write_source_value(self, "departure_meter", value)

    @property
    def return_meter(self):
        from app.modules.meter_readings.source_values import read_source_value
        return read_source_value(self, "return_meter")

    @return_meter.setter
    def return_meter(self, value):
        from app.modules.meter_readings.source_values import write_source_value
        write_source_value(self, "return_meter", value)
