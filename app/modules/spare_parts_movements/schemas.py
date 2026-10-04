from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

MOVEMENT_TYPES = {"distribution", "return"}

class MovementItemCreate(BaseModel):
    request_item_id: int
    quantity: Decimal = Field(gt=0)
    notes: str | None = None

class MovementDocumentCreate(BaseModel):
    document_number: str = Field(min_length=1, max_length=80)
    document_type: str
    document_date: date
    issuer: str = Field(min_length=1, max_length=160)
    recipient: str = Field(min_length=1, max_length=160)
    beneficiary: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    items: list[MovementItemCreate] = Field(min_length=1)

    @field_validator("document_number", "issuer", "recipient", mode="before")
    @classmethod
    def strip_required(cls, value):
        return str(value).strip() if value is not None else value

    @field_validator("document_type")
    @classmethod
    def valid_type(cls, value):
        if value not in MOVEMENT_TYPES:
            raise ValueError("نوع الوثيقة غير صالح")
        return value

class MovementItemOut(BaseModel):
    id: int
    request_item_id: int
    part_name: str | None = None
    request_number: str | None = None
    quantity: Decimal
    notes: str | None = None
    model_config = {"from_attributes": True}

class MovementDocumentOut(BaseModel):
    id: int
    document_number: str
    document_type: str
    document_date: date
    issuer: str
    recipient: str
    beneficiary: str | None = None
    notes: str | None = None
    items: list[MovementItemOut]
    model_config = {"from_attributes": True}
