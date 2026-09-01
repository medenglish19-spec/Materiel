from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


FAULT_SEVERITIES = {"low", "medium", "high", "critical"}
FAULT_STATUSES = {"open", "diagnosing", "repairing", "waiting_parts", "repaired", "closed"}
FAULT_EXPLOITATION_IMPACTS = {"none", "limited", "prohibited"}
REPAIR_STATUSES = {"in_progress", "completed", "cancelled"}
WORKSHOP_TYPES = {"internal", "external"}


class FaultCreate(BaseModel):
    equipment_id: int
    maintenance_record_id: Optional[int] = None
    reported_date: date
    meter_value: Optional[Decimal] = Field(default=None, ge=0)
    fault_type: Optional[str] = None
    description: str = Field(min_length=1)
    severity: str = "medium"
    exploitation_impact: str = "none"
    report_number: Optional[str] = None
    note: Optional[str] = None

    @field_validator("exploitation_impact")
    @classmethod
    def valid_exploitation_impact(cls, v):
        if v not in FAULT_EXPLOITATION_IMPACTS:
            raise ValueError("تأثير العطل على الاستغلال غير صحيح")
        return v

    @field_validator("severity")
    @classmethod
    def valid_severity(cls, v):
        if v not in FAULT_SEVERITIES:
            raise ValueError("درجة الخطورة غير صحيحة")
        return v


class FaultUpdate(BaseModel):
    reported_date: Optional[date] = None
    meter_value: Optional[Decimal] = Field(default=None, ge=0)
    fault_type: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    exploitation_impact: Optional[str] = None
    report_number: Optional[str] = None
    note: Optional[str] = None

    @field_validator("exploitation_impact")
    @classmethod
    def valid_exploitation_impact(cls, v):
        if v is not None and v not in FAULT_EXPLOITATION_IMPACTS:
            raise ValueError("تأثير العطل على الاستغلال غير صحيح")
        return v


class FaultStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v not in FAULT_STATUSES:
            raise ValueError("حالة العطل غير صحيحة")
        return v


class FaultOut(FaultCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    created_at: datetime
    updated_at: datetime


class RepairCreate(BaseModel):
    fault_id: int
    repair_date: date
    meter_value: Optional[Decimal] = Field(default=None, ge=0)
    diagnosis: Optional[str] = None
    action_taken: str = Field(min_length=1)
    technician: Optional[str] = None
    workshop_type: str = "internal"
    workshop: Optional[str] = None
    repair_document: Optional[str] = None
    external_dispatch_document: Optional[str] = None
    labor_hours: Optional[Decimal] = Field(default=None, ge=0)
    status: str = "completed"
    notes: Optional[str] = None

    @field_validator("workshop_type")
    @classmethod
    def valid_workshop(cls, v):
        if v not in WORKSHOP_TYPES:
            raise ValueError("نوع الورشة غير صحيح")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v not in REPAIR_STATUSES:
            raise ValueError("حالة الإصلاح غير صحيحة")
        return v


class RepairOut(RepairCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class SparePartCreate(BaseModel):
    part_number: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    receiving_document: str = Field(min_length=1, max_length=255)
    notes: Optional[str] = None


class SparePartUpdate(BaseModel):
    part_number: Optional[str] = None
    name: Optional[str] = None
    receiving_document: Optional[str] = None
    notes: Optional[str] = None


class SparePartOut(SparePartCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RepairPartCreate(BaseModel):
    repair_id: int
    spare_part_id: int
    quantity: Decimal = Field(gt=0)
    distribution_document: str = Field(min_length=1, max_length=255)
    notes: Optional[str] = None


class RepairPartOut(RepairPartCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TechnicianCreate(BaseModel):
    employee_number: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=160)
    specialization: Optional[str] = Field(default=None, max_length=120)
    is_active: bool = True
    notes: Optional[str] = None

class TechnicianUpdate(BaseModel):
    full_name: Optional[str] = None
    specialization: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

class TechnicianOut(TechnicianCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class TechnicianInterventionCreate(BaseModel):
    repair_id: int
    technician_id: int
    intervention_date: date
    hours: Decimal = Field(ge=0)
    work_description: Optional[str] = None
    notes: Optional[str] = None

class TechnicianInterventionOut(TechnicianInterventionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RepairStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v):
        if v not in REPAIR_STATUSES:
            raise ValueError("حالة الإصلاح غير صحيحة")
        return v
