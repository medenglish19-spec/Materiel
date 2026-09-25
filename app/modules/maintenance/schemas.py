from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _positive(value, field_name):
    if value is not None and value <= 0:
        raise ValueError(f"{field_name} يجب أن يكون أكبر من صفر")
    return value


def _nonnegative(value, field_name):
    if value is not None and value < 0:
        raise ValueError(f"{field_name} لا يمكن أن يكون سالبًا")
    return value


class MaintenanceOperationGroupBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = 0


class MaintenanceOperationGroupCreate(MaintenanceOperationGroupBase):
    pass


class MaintenanceOperationGroupUpdate(MaintenanceOperationGroupBase):
    pass


class MaintenanceOperationGroupOut(MaintenanceOperationGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MaintenanceOperationBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    interval_km: Optional[Decimal] = None
    interval_hours: Optional[Decimal] = None
    interval_days: Optional[int] = None
    warning_km: Optional[Decimal] = None
    warning_days: Optional[int] = None
    is_active: bool = True
    description: Optional[str] = None
    group_id: Optional[int] = None

    @field_validator("interval_km")
    @classmethod
    def interval_km_valid(cls, value):
        return _positive(value, "فترة الكيلومترات")

    @field_validator("interval_hours")
    @classmethod
    def interval_hours_valid(cls, value):
        return _positive(value, "فترة الساعات")

    @field_validator("interval_days")
    @classmethod
    def interval_days_valid(cls, value):
        return _positive(value, "فترة الأيام")

    @field_validator("warning_km")
    @classmethod
    def warning_km_valid(cls, value):
        return _nonnegative(value, "تنبيه الكيلومترات")

    @field_validator("warning_days")
    @classmethod
    def warning_days_valid(cls, value):
        return _nonnegative(value, "تنبيه الأيام")

    @model_validator(mode="after")
    def validate_interval_presence(self):
        if self.interval_km is None and self.interval_hours is None and self.interval_days is None:
            raise ValueError("يجب تحديد شرط زمني واحد على الأقل للعملية")
        return self


class MaintenanceOperationCreate(MaintenanceOperationBase):
    old_rule_id: Optional[int] = None


class MaintenanceOperationUpdate(MaintenanceOperationBase):
    old_rule_id: Optional[int] = None


class MaintenanceOperationOut(MaintenanceOperationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    old_rule_id: Optional[int] = None


class MaintenancePlanBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    equipment_model_id: int
    interval_km: Optional[Decimal] = None
    interval_hours: Optional[Decimal] = None
    interval_days: Optional[int] = None
    is_active: bool = True
    description: Optional[str] = None

    @field_validator("interval_km")
    @classmethod
    def interval_km_valid(cls, value):
        return _positive(value, "فترة الخطة بالكيلومترات")

    @field_validator("interval_hours")
    @classmethod
    def interval_hours_valid(cls, value):
        return _positive(value, "فترة الخطة بالساعات")

    @field_validator("interval_days")
    @classmethod
    def interval_days_valid(cls, value):
        return _positive(value, "فترة الخطة بالأيام")


class MaintenancePlanCreate(MaintenancePlanBase):
    pass


class MaintenancePlanUpdate(MaintenancePlanBase):
    pass


class MaintenancePlanOut(MaintenancePlanBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MaintenancePlanOperationBase(BaseModel):
    plan_id: int
    operation_id: int
    sort_order: int = 0
    interval_km_override: Optional[Decimal] = None
    interval_hours_override: Optional[Decimal] = None
    interval_days_override: Optional[int] = None

    @field_validator("interval_km_override")
    @classmethod
    def km_override_valid(cls, value):
        return _positive(value, "تجاوز فترة الكيلومترات")

    @field_validator("interval_hours_override")
    @classmethod
    def hours_override_valid(cls, value):
        return _positive(value, "تجاوز فترة الساعات")

    @field_validator("interval_days_override")
    @classmethod
    def days_override_valid(cls, value):
        return _positive(value, "تجاوز فترة الأيام")


class MaintenancePlanOperationCreate(MaintenancePlanOperationBase):
    pass


class MaintenancePlanOperationOut(MaintenancePlanOperationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MaintenanceRecordCreate(BaseModel):
    equipment_id: int
    rule_id: Optional[int] = None
    operation_id: Optional[int] = None
    plan_id: Optional[int] = None
    maintenance_date: date
    reported_date: Optional[date] = None
    meter_value: Optional[Decimal] = None
    work_order: Optional[str] = None
    workshop: Optional[str] = None
    status: Optional[str] = None
    is_scheduled: bool = False
    description: Optional[str] = None

    @field_validator("meter_value")
    @classmethod
    def meter_valid(cls, value):
        return _nonnegative(value, "قراءة العداد")

    @model_validator(mode="after")
    def validate_source(self):
        if self.rule_id is None and self.operation_id is None:
            raise ValueError("يجب تحديد عملية الصيانة أو الصيانة الدورية")
        return self


class MaintenanceRecordOut(MaintenanceRecordCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_id: Optional[int] = None
    created_at: object


class MaintenanceOperationRuleMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    old_rule_id: int
    operation_id: int
