from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

MEASUREMENT_UNITS = {"km", "hours"}
MOBILITY_TYPES = {"mobile", "towed"}
SPEC_DATA_TYPES = {"text", "number", "select"}

class EquipmentCategoryCreate(BaseModel):
    name: str
    code: Optional[str] = None
class EquipmentCategoryUpdate(BaseModel):
    name: str
    code: Optional[str] = None
class EquipmentCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; name: str; code: str; sort_order: int; is_system: bool
class EquipmentBrandCreate(BaseModel):
    name: str
class EquipmentBrandUpdate(BaseModel):
    name: str
class EquipmentBrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; name: str; is_active: bool
class EquipmentTypeCreate(BaseModel):
    name: str; measurement_unit: str; category_id: int; theoretical_quantity: Optional[int] = None
    @field_validator("measurement_unit")
    @classmethod
    def measurement_unit_valid(cls, v: str) -> str:
        if v not in MEASUREMENT_UNITS: raise ValueError(f"وحدة القياس يجب أن تكون أحد: {MEASUREMENT_UNITS}")
        return v
    @field_validator("theoretical_quantity")
    @classmethod
    def theoretical_quantity_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0: raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
        return v
class EquipmentTypeUpdate(BaseModel):
    name: str; measurement_unit: str; category_id: int; theoretical_quantity: Optional[int] = None
    @field_validator("measurement_unit")
    @classmethod
    def measurement_unit_valid(cls, v: str) -> str:
        if v not in MEASUREMENT_UNITS: raise ValueError("وحدة القياس غير صحيحة")
        return v
    @field_validator("theoretical_quantity")
    @classmethod
    def theoretical_quantity_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0: raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
        return v
class EquipmentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; name: str; measurement_unit: str; theoretical_quantity: Optional[int] = None; category_id: Optional[int] = None; is_frozen: bool
POSITION_SIDES = {"left", "right"}
POSITION_TYPES = {"single", "inner", "outer"}

class TirePositionInput(BaseModel):
    id: Optional[int] = None
    axle_number: int
    side: str
    position_type: str
    description: Optional[str] = None
    @field_validator("side")
    @classmethod
    def side_valid(cls, v: str) -> str:
        if v not in POSITION_SIDES: raise ValueError("جهة الموضع غير صالحة")
        return v
    @field_validator("position_type")
    @classmethod
    def type_valid(cls, v: str) -> str:
        if v not in POSITION_TYPES: raise ValueError("نوع الموضع غير صالح")
        return v
    @field_validator("axle_number")
    @classmethod
    def axle_valid(cls, v: int) -> int:
        if v < 1: raise ValueError("رقم المحور غير صالح")
        return v

class SpecDefinitionCreate(BaseModel):
    name: str
    data_type: str = "text"
    unit: Optional[str] = None
    options: Optional[str] = None
    @field_validator("data_type")
    @classmethod
    def data_type_valid(cls,v: str) -> str:
        if v not in SPEC_DATA_TYPES: raise ValueError(f"نوع الخاصية يجب أن يكون أحد: {SPEC_DATA_TYPES}")
        return v

class SpecDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    data_type: str
    unit: Optional[str]
    options: Optional[str]
    sort_order: int

class SpecValueInput(BaseModel):
    definition_id: int
    value: str

class EquipmentModelCreate(BaseModel):
    name: str
    equipment_type_id: int
    brand_id: int
    has_tires: bool = False
    tire_positions_required: int = 0
    axle_count: Optional[int] = None
    tire_size: Optional[str] = None
    has_batteries: bool = False
    battery_count_required: int = 0
    battery_capacity_ah: Optional[float] = None
    battery_voltage_v: Optional[float] = None
    mobility_type: str = "mobile"
    requires_driver: bool = True
    positions: list[TirePositionInput] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    specs: list[SpecValueInput] = Field(default_factory=list)
    @field_validator("tire_positions_required", "battery_count_required")
    @classmethod
    def counts_valid(cls, v: int) -> int:
        if v < 0: raise ValueError("عدد التجهيزات لا يمكن أن يكون سالبًا")
        return v
    @field_validator("axle_count")
    @classmethod
    def axle_count_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1: raise ValueError("عدد المحاور يجب أن يكون رقمًا موجبًا")
        return v
    @field_validator("tire_size")
    @classmethod
    def tire_size_valid(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v is not None else None
    @field_validator("battery_capacity_ah", "battery_voltage_v")
    @classmethod
    def positive_specs(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0: raise ValueError("قيمة البطارية يجب أن تكون أكبر من صفر")
        return v
    @field_validator("mobility_type")
    @classmethod
    def mobility_valid(cls, v: str) -> str:
        if v not in MOBILITY_TYPES: raise ValueError("يجب تحديد ما إذا كان العتاد متحركًا أو مجرورًا")
        return v
class EquipmentModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; name: str; equipment_type_id: int; brand_id: Optional[int] = None; is_frozen: bool; has_tires: bool; tire_positions_required: int; axle_count: Optional[int]; tire_size: Optional[str]; has_batteries: bool; battery_count_required: int; battery_capacity_ah: Optional[float]; battery_voltage_v: Optional[float]; mobility_type: str; requires_driver: bool