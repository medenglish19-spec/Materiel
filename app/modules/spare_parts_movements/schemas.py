from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator

MOVEMENT_TYPES = {"distribution", "return"}

class MovementItemCreate(BaseModel):
    request_item_id: int
    quantity: Decimal = Field(gt=0)
    source_item_id: int | None = None
    notes: str | None = None

class MovementDocumentCreate(BaseModel):
    document_number: str = Field(min_length=1, max_length=80)
    document_type: str
    document_date: date
    issuer: str | None = Field(default=None, max_length=160)
    recipient: str | None = Field(default=None, max_length=160)
    beneficiary: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    source_document_id: int | None = None
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

    @model_validator(mode="after")
    def source_rules(self):
        if self.document_type == "distribution" and self.source_document_id is not None:
            raise ValueError("التوزيع لا يرتبط بوثيقة حركة سابقة")
        if self.document_type == "return" and self.source_document_id is None:
            raise ValueError("الإرجاع يجب أن يرتبط بوثيقة توزيع")
        return self


class MovementDocumentUpdate(BaseModel):
    document_number: str | None = Field(default=None, min_length=1, max_length=80)
    document_date: date | None = None
    recipient: str | None = Field(default=None, max_length=160)
    beneficiary: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    source_document_id: int | None = None
    items: list[MovementItemCreate] | None = Field(default=None, min_length=1)

    @field_validator("document_number", "recipient", mode="before")
    @classmethod
    def strip_update(cls, value):
        return str(value).strip() if value is not None else value


class MovementItemOut(BaseModel):
    id: int
    request_item_id: int
    source_item_id: int | None = None
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
    source_document_id: int | None = None
    items: list[MovementItemOut]
    model_config = {"from_attributes": True}
