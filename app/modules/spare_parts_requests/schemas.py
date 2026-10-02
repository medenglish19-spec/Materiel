from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


REQUEST_STATUSES = {"pending", "approved", "partially_fulfilled", "fulfilled", "rejected", "cancelled"}
SOURCE_TYPES = {"maintenance", "repair", "tire", "battery"}


class SparePartRequestItemCreate(BaseModel):
    spare_part_id: int
    requested_quantity: Decimal = Field(gt=0)
    notes: str | None = None


class SparePartRequestCreate(BaseModel):
    request_date: date
    needed_by_date: date | None = None
    source_type: str
    source_id: int
    equipment_id: int | None = None
    priority: str = "normal"
    notes: str | None = None
    items: list[SparePartRequestItemCreate] = Field(min_length=1)


class SparePartRequestItemUpdate(BaseModel):
    approved_quantity: Decimal = Field(ge=0)
    issued_quantity: Decimal = Field(ge=0)
    notes: str | None = None


class SparePartRequestStatusUpdate(BaseModel):
    status: str


class SparePartRequestItemOut(BaseModel):
    id: int
    spare_part_id: int
    requested_quantity: Decimal
    approved_quantity: Decimal
    issued_quantity: Decimal
    notes: str | None = None

    model_config = {"from_attributes": True}


class SparePartRequestOut(BaseModel):
    id: int
    request_number: str
    request_date: date
    needed_by_date: date | None
    source_type: str
    maintenance_record_id: int | None
    repair_id: int | None
    tire_id: int | None
    battery_id: int | None
    equipment_id: int | None
    priority: str
    status: str
    requested_by_id: int | None
    notes: str | None
    items: list[SparePartRequestItemOut]

    model_config = {"from_attributes": True}
