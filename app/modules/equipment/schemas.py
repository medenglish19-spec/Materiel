from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


TECHNICAL_CONDITIONS = {
    "ready",
    "ready_restricted",
    "broken",
}

OPERATIONAL_STATUSES = {
    "available",
    "in_mission",
    "in_maintenance",
    "in_external_workshop",
    "unavailable",
}


class EquipmentBase(BaseModel):
    acquisition_document: Optional[str] = None
    registration_number: Optional[str] = None
    vin: Optional[str] = None

    equipment_type_id: int
    equipment_model_id: Optional[int] = None

    acquisition_date: Optional[date] = None

    technical_condition: str = "ready"
    operational_status: str = "available"

    current_odometer: Optional[Decimal] = Field(
        default=Decimal("0"),
        ge=0,
    )

    current_hours: Optional[Decimal] = Field(
        default=Decimal("0"),
        ge=0,
    )

    notes: Optional[str] = None

    @field_validator("technical_condition")
    @classmethod
    def technical_condition_valid(cls, v: str) -> str:
        if v not in TECHNICAL_CONDITIONS:
            raise ValueError(
                f"الحالة الفنية يجب أن تكون أحد: {TECHNICAL_CONDITIONS}"
            )

        return v

    @field_validator("operational_status")
    @classmethod
    def operational_status_valid(cls, v: str) -> str:
        if v not in OPERATIONAL_STATUSES:
            raise ValueError(
                f"الوضعية يجب أن تكون أحد: {OPERATIONAL_STATUSES}"
            )

        return v


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    acquisition_document: Optional[str] = None
    registration_number: Optional[str] = None
    vin: Optional[str] = None

    equipment_type_id: Optional[int] = None
    equipment_model_id: Optional[int] = None

    acquisition_date: Optional[date] = None

    technical_condition: Optional[str] = None
    operational_status: Optional[str] = None

    current_odometer: Optional[Decimal] = Field(
        default=None,
        ge=0,
    )

    current_hours: Optional[Decimal] = Field(
        default=None,
        ge=0,
    )

    notes: Optional[str] = None

    @field_validator("technical_condition")
    @classmethod
    def technical_condition_valid(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if (
            v is not None
            and v not in TECHNICAL_CONDITIONS
        ):
            raise ValueError(
                f"الحالة الفنية يجب أن تكون أحد: {TECHNICAL_CONDITIONS}"
            )

        return v

    @field_validator("operational_status")
    @classmethod
    def operational_status_valid(
        cls,
        v: Optional[str],
    ) -> Optional[str]:

        if (
            v is not None
            and v not in OPERATIONAL_STATUSES
        ):
            raise ValueError(
                f"الوضعية يجب أن تكون أحد: {OPERATIONAL_STATUSES}"
            )

        return v


class EquipmentOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    asset_code: str

    acquisition_document: Optional[str] = None
    registration_number: Optional[str] = None
    vin: Optional[str] = None

    equipment_type_id: int
    equipment_model_id: Optional[int] = None

    technical_condition: str
    operational_status: str

    current_odometer: Optional[Decimal] = None
    current_hours: Optional[Decimal] = None

    notes: Optional[str] = None

    created_at: datetime
    updated_at: datetime
