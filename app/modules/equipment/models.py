from sqlalchemy import Column, Integer, String, Date, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database.base import Base
from app.shared.mixins import AuditMixin


class Equipment(Base, AuditMixin):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)

    asset_code = Column(String(50), unique=True, index=True, nullable=False)
    acquisition_document = Column(String(100), nullable=True)
    registration_number = Column(String(30), unique=True, index=True, nullable=True)
    vin = Column(String(50), unique=True, nullable=True)

    equipment_type_id = Column(Integer, ForeignKey("equipment_types.id"), nullable=False)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id"), nullable=True)

    equipment_type = relationship("EquipmentType")
    equipment_model = relationship("EquipmentModel")
    maintenance_records = relationship("MaintenanceRecord", back_populates="equipment", order_by="MaintenanceRecord.maintenance_date.desc(), MaintenanceRecord.id.desc()")

    acquisition_date = Column(Date, nullable=True)

    technical_condition = Column(String(20), nullable=False, default="ready")
    operational_status = Column(String(30), nullable=False, default="available")

    current_odometer = Column(Numeric(10, 1), nullable=True, default=0)
    current_hours = Column(Numeric(10, 1), nullable=True, default=0)

    notes = Column(String(500), nullable=True)
