from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator

MEASUREMENT_UNITS = {"km", "hours"}


class EquipmentCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str
    sort_order: int
    is_system: bool


class EquipmentBrandCreate(BaseModel):
    name: str


class EquipmentBrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool


class EquipmentTypeCreate(BaseModel):
    name: str
    measurement_unit: str
    category_id: Optional[int] = None

    @field_validator("measurement_unit")
    @classmethod
    def measurement_unit_valid(cls, v: str) -> str:
        if v not in MEASUREMENT_UNITS:
            raise ValueError(f"وحدة القياس يجب أن تكون أحد: {MEASUREMENT_UNITS}")
        return v


class EquipmentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    measurement_unit: str
    category_id: Optional[int] = None


class EquipmentModelCreate(BaseModel):
    name: str
    equipment_type_id: int
    brand_id: Optional[int] = None
    theoretical_quantity: int = 0


class EquipmentModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    equipment_type_id: int
    brand_id: Optional[int] = None
