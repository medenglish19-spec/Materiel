from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator


REQUEST_STATUSES = {"pending", "approved", "rejected", "cancelled"}
SOURCE_TYPES = {"fault", "repair"}


class SparePartRequestItemCreate(BaseModel):
    spare_part_id: int | None = None
    spare_part_name: str | None = Field(default=None, max_length=160)
    requested_quantity: int = Field(gt=0)
    received_quantity: int = Field(default=0, ge=0)
    received_date: date | None = None
    recipient: str | None = None
    supplier_institution: str | None = None
    notes: str | None = None

    @field_validator("spare_part_name")
    @classmethod
    def clean_name(cls, value):
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def part_reference_present(self):
        if not self.spare_part_id and not self.spare_part_name:
            raise ValueError("اسم قطعة الغيار مطلوب")
        return self


class SparePartRequestCreate(BaseModel):
    request_number: str = Field(min_length=1, max_length=80)
    request_date: date
    source_type: str
    source_id: int
    notes: str | None = None
    items: list[SparePartRequestItemCreate] = Field(default_factory=list)

    @field_validator("source_type")
    @classmethod
    def valid_source(cls, value):
        if value not in SOURCE_TYPES:
            raise ValueError("مصدر طلب الغيار غير صالح")
        return value


class SparePartRequestUpdate(BaseModel):
    request_number: str | None = Field(default=None, min_length=1, max_length=80)
    request_date: date | None = None
    notes: str | None = None


class SparePartRequestItemUpdate(BaseModel):
    spare_part_id: int | None = None
    spare_part_name: str | None = Field(default=None, max_length=160)
    requested_quantity: int | None = Field(default=None, gt=0)
    received_quantity: int | None = Field(default=None, ge=0)
    received_date: date | None = None
    recipient: str | None = None
    supplier_institution: str | None = None
    notes: str | None = None

    @field_validator("spare_part_name")
    @classmethod
    def clean_name(cls, value):
        if value is None:
            return None
        return value.strip() or None


class SparePartRequestStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in REQUEST_STATUSES:
            raise ValueError("حالة طلب الغيار غير صالحة")
        return value


class SparePartRequestItemOut(BaseModel):
    id: int
    spare_part_id: int | None
    spare_part_name: str | None = None
    requested_quantity: Decimal
    received_quantity: Decimal
    received_date: date | None = None
    recipient: str | None = None
    supplier_institution: str | None = None
    notes: str | None = None
    part_name: str | None = None

    model_config = {"from_attributes": True}


class SparePartRequestOut(BaseModel):
    id: int
    request_number: str
    request_date: date
    source_type: str
    fault_id: int | None
    repair_id: int | None
    equipment_id: int | None
    equipment_code: str | None = None
    equipment_registration: str | None = None
    report_number: str | None = None
    status: str
    notes: str | None
    items: list[SparePartRequestItemOut]

    model_config = {"from_attributes": True}
