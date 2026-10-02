from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


REQUEST_STATUSES = {"pending", "approved", "rejected", "cancelled"}
SOURCE_TYPES = {"fault", "repair"}


class SparePartRequestItemCreate(BaseModel):
    spare_part_id: int
    # الكميات أعداد صحيحة: المطلوبة 1 فأكثر، والمستلمة 0 فأكثر (صفر = لم يُستلم بعد).
    requested_quantity: int = Field(gt=0)
    received_quantity: int = Field(default=0, ge=0)
    received_date: date | None = None
    recipient: str | None = None
    supplier_institution: str | None = None
    notes: str | None = None


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


class SparePartRequestItemUpdate(BaseModel):
    requested_quantity: int | None = Field(default=None, gt=0)
    received_quantity: int | None = Field(default=None, ge=0)
    received_date: date | None = None
    recipient: str | None = None
    supplier_institution: str | None = None
    notes: str | None = None


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
    spare_part_id: int
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
