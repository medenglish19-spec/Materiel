from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.shared.mixins import AuditMixin


class Mission(Base, AuditMixin):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(
        Integer,
        ForeignKey(
            "drivers.id",
            ondelete="SET NULL",
            name="fk_missions_driver_id_drivers",
        ),
        nullable=True,
        index=True,
    )
    driver_name = Column(String(120), nullable=True)
    mission_document = Column(String(100), nullable=True)
    purpose = Column(String(250), nullable=True)
    destination = Column(String(150), nullable=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    equipment = relationship("Equipment")
    driver = relationship("Driver")

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


class Driver(Base, AuditMixin):
    __tablename__ = "drivers"
    __table_args__ = (
        UniqueConstraint("employee_number", name="uq_drivers_employee_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_number = Column(String(50), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    center = Column(String(120), nullable=True)
    license_class = Column(String(50), nullable=False)
    license_issue_date = Column(Date, nullable=True)
    license_expiry_date = Column(Date, nullable=True)
    assigned_equipment_id = Column(
        Integer,
        ForeignKey(
            "equipment.id",
            ondelete="SET NULL",
            name="fk_drivers_assigned_equipment_id_equipment",
        ),
        nullable=True,
        index=True,
    )
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    assigned_equipment = relationship("Equipment")


class DriverSystemSetting(Base, AuditMixin):
    __tablename__ = "driver_system_settings"

    id = Column(Integer, primary_key=True)
    center_column_label = Column(
        String(100), nullable=False, default="المركز", server_default="المركز"
    )
