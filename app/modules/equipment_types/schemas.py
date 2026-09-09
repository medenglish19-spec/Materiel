from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator

MEASUREMENT_UNITS = {"km", "hours"}
MOBILITY_TYPES = {"mobile", "towed"}

class EquipmentCategoryCreate(BaseModel):
    name: str
    code: Optional[str] = None

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
    category_id: int
    theoretical_quantity: Optional[int] = None
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

class EquipmentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    measurement_unit: str
    theoretical_quantity: Optional[int] = None
    category_id: int

class EquipmentModelCreate(BaseModel):
    name: str
    equipment_type_id: int
    brand_id: int
    has_tires: bool = False
    tire_positions_required: int = 0
    has_batteries: bool = False
    battery_count_required: int = 0
    mobility_type: str
    requires_driver: bool
    @field_validator("tire_positions_required", "battery_count_required")
    @classmethod
    def counts_valid(cls, v: int) -> int:
        if v < 0: raise ValueError("عدد التجهيزات لا يمكن أن يكون سالبًا")
        return v
    @field_validator("mobility_type")
    @classmethod
    def mobility_valid(cls, v: str) -> str:
        if v not in MOBILITY_TYPES: raise ValueError("يجب تحديد ما إذا كان العتاد متحركًا أو مجرورًا")
        return v
    def validate_component_requirements(self):
        if self.has_tires and self.tire_positions_required < 1: raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد عدد مواضع الإطارات")
        if not self.has_tires and self.tire_positions_required != 0: raise ValueError("عدد مواضع الإطارات يجب أن يكون صفرًا إذا كان الطراز لا يملك إطارات")
        if self.has_batteries and self.battery_count_required < 1: raise ValueError("هذا الطراز يملك بطاريات؛ يجب تحديد عدد البطاريات")
        if not self.has_batteries and self.battery_count_required != 0: raise ValueError("عدد البطاريات يجب أن يكون صفرًا إذا كان الطراز لا يملك بطاريات")

class EquipmentModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    equipment_type_id: int
    brand_id: int
    has_tires: bool
    tire_positions_required: int
    has_batteries: bool
    battery_count_required: int
    mobility_type: str
    requires_driver: bool
