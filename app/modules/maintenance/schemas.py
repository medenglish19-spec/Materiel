from datetime import date
from decimal import Decimal
from typing import Literal, Optional

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


class MaintenanceOperationModelConditionIn(BaseModel):
    """Condition settings of one operation for one equipment model.

    Both `condition_source` states are meaningful:
      * "unset" → nothing stored for this model yet;
      * "model" → stored for this model (empty columns are then deliberate).
    Warning settings are unified at the operation level.
    """

    model_id: int
    condition_source: Literal["unset", "model"] = "model"
    interval_km: Optional[Decimal] = None
    interval_hours: Optional[Decimal] = None
    interval_days: Optional[int] = None

    @field_validator("interval_km")
    @classmethod
    def model_interval_km_valid(cls, value):
        return _positive(value, "فترة كيلومترات الطراز")

    @field_validator("interval_hours")
    @classmethod
    def model_interval_hours_valid(cls, value):
        return _positive(value, "فترة ساعات الطراز")

    @field_validator("interval_days")
    @classmethod
    def model_interval_days_valid(cls, value):
        return _positive(value, "فترة أيام الطراز")


class MaintenanceOperationModelConditionOut(BaseModel):
    model_id: int
    model_name: Optional[str] = None
    condition_source: Literal["unset", "model"] = "unset"
    interval_km: Optional[Decimal] = None
    interval_hours: Optional[Decimal] = None
    interval_days: Optional[int] = None
    # هل حُفظ شرط لهذا الطراز أصلًا؟ يفرّق بين «غير محدد» و«محدد بلا إنذار».
    is_defined: bool = False
    condition_text: str = "—"
    unit_text: str = "—"
    condition_units: list[str] = Field(default_factory=list)
    # Warning text (unified at operation level, shown for each model)
    warning_text: str = "—"


class MaintenanceOperationConditionSummaryOut(BaseModel):
    """Display-ready summary of the models' conditions for the library table."""

    models_count: int = 0
    defined_count: int = 0
    unset_count: int = 0
    condition: Optional[str] = None
    condition_state: str = "no_models"
    warning: Optional[str] = None
    warning_state: str = "no_models"
    unit: Optional[str] = None
    has_multiple_conditions: bool = False
    has_multiple_warnings: bool = False


class MaintenanceOperationBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # أعمدة قديمة مشتركة على العملية: تبقى في المخطط ولا تُستخدم في أي حساب،
    # ولذلك لا يُشترط وجود قيمة فيها. شرط الاستحقاق الفعلي يخص كل طراز.
    interval_km: Optional[Decimal] = None
    interval_hours: Optional[Decimal] = None
    interval_days: Optional[int] = None
    warning_km: Optional[Decimal] = None
    warning_days: Optional[int] = None
    is_active: bool = True
    description: Optional[str] = None
    group_id: Optional[int] = None
    # Per-model conditions: the authoritative eligibility data.
    equipment_model_conditions: list[MaintenanceOperationModelConditionIn] = Field(default_factory=list)

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


class MaintenanceOperationCreate(MaintenanceOperationBase):
    pass


class MaintenanceOperationUpdate(MaintenanceOperationBase):
    # عند تعديل العملية العامة من المكتبة لا تُرسل شروط الطرازات أصلًا. غياب
    # الحقل يعني «لا تلمس ارتباطات الطرازات الحالية»، وليس «احذفها». الـAPI
    # يبقى قادرًا على حذف ربط صريح عند إرسال قائمة فعلية.
    equipment_model_conditions: Optional[list[MaintenanceOperationModelConditionIn]] = None


class MaintenanceOperationOut(MaintenanceOperationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    # الأعمدة القديمة المشتركة على العملية مُهملة في كل عرض تشغيلي، فهي لا
    # تُرسل في استجابة الـAPI إطلاقًا (تبقى في قاعدة البيانات كما هي).
    interval_km: Optional[Decimal] = Field(default=None, exclude=True)
    interval_hours: Optional[Decimal] = Field(default=None, exclude=True)
    interval_days: Optional[int] = Field(default=None, exclude=True)
    # warning_km و warning_days هي حقول الإنذار الموحدة على مستوى العملية — تُعرض في الاستجابة.
    warning_km: Optional[Decimal] = None
    warning_days: Optional[int] = None
    # شروط الطرازات: تُبنى في الـ router/الخدمة، لا من خصائص ORM مباشرة.
    model_conditions: list[MaintenanceOperationModelConditionOut] = Field(default_factory=list)
    condition_summary: MaintenanceOperationConditionSummaryOut = Field(
        default_factory=MaintenanceOperationConditionSummaryOut
    )
    # مصدر الشرط: شروط محفوظة على علاقات الطرازات، أو لا شرط محفوظ لأي طراز.
    condition_source: Literal["model_conditions", "none"] = "none"


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
    is_approved: bool = False


class MaintenancePlanBulkDelete(BaseModel):
    """طلب حذف جماعي لخطط الصيانة المحددة.

    تُرد الخطط غير الموجودة داخل ``rejected`` مع سببها، وتُحذف البقية. لا يمس
    الحذف سجلات الصيانة التاريخية ولا تعريفات العمليات في المكتبة.
    """

    plan_ids: list[int] = Field(min_length=1)

    @field_validator("plan_ids")
    @classmethod
    def plan_ids_valid(cls, value):
        if any(plan_id <= 0 for plan_id in value):
            raise ValueError("معرّفات الخطط يجب أن تكون أكبر من صفر")
        if len(value) != len(set(value)):
            raise ValueError("لا يمكن تكرار معرّف الخطة في الطلب نفسه")
        return value


class MaintenanceOperationBulkDelete(BaseModel):
    operation_ids: list[int] = Field(min_length=1)

    @field_validator("operation_ids")
    @classmethod
    def operation_ids_valid(cls, value):
        if any(operation_id <= 0 for operation_id in value):
            raise ValueError("معرّفات العمليات يجب أن تكون أكبر من صفر")
        if len(value) != len(set(value)):
            raise ValueError("لا يمكن تكرار معرّف العملية في الطلب نفسه")
        return value


class MaintenanceRecordBulkDelete(BaseModel):
    record_ids: list[int] = Field(min_length=1)

    @field_validator("record_ids")
    @classmethod
    def record_ids_valid(cls, value):
        if any(record_id <= 0 for record_id in value):
            raise ValueError("معرّفات سجلات الصيانة يجب أن تكون أكبر من صفر")
        if len(value) != len(set(value)):
            raise ValueError("لا يمكن تكرار معرّف السجل في الطلب نفسه")
        return value


class MaintenancePlanOperationBase(BaseModel):
    plan_id: int
    operation_id: int
    sort_order: int = 0

class MaintenancePlanOperationCreate(MaintenancePlanOperationBase):
    pass


class MaintenancePlanOperationsBulkCreate(BaseModel):
    operation_ids: list[int] = Field(min_length=1)

    @field_validator("operation_ids")
    @classmethod
    def operation_ids_are_unique_positive(cls, value):
        if any(operation_id <= 0 for operation_id in value):
            raise ValueError("معرّفات العمليات يجب أن تكون موجبة")
        if len(value) != len(set(value)):
            raise ValueError("لا يمكن تكرار معرّف العملية في الطلب نفسه")
        return value


class MaintenanceOperationModelConditionSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_km: Optional[Decimal] = None
    interval_hours: Optional[Decimal] = None
    interval_days: Optional[int] = None

    @field_validator("interval_km")
    @classmethod
    def interval_km_positive(cls, value):
        if value is not None and not value.is_finite():
            raise ValueError("فترة الكيلومترات يجب أن تكون رقمًا محدودًا")
        return _positive(value, "فترة الكيلومترات")

    @field_validator("interval_hours")
    @classmethod
    def interval_hours_positive(cls, value):
        if value is not None and not value.is_finite():
            raise ValueError("فترة الساعات يجب أن تكون رقمًا محدودًا")
        return _positive(value, "فترة الساعات")

    @field_validator("interval_days")
    @classmethod
    def interval_days_positive(cls, value):
        return _positive(value, "فترة الأيام")

    @model_validator(mode="after")
    def require_interval(self):
        if self.interval_km is None and self.interval_hours is None and self.interval_days is None:
            raise ValueError("يجب تحديد فاصل استحقاق واحد على الأقل")
        return self


class MaintenancePlanOperationOut(MaintenancePlanOperationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MaintenanceRecordCreate(BaseModel):
    equipment_id: int
    operation_id: Optional[int] = None
    plan_id: Optional[int] = None
    maintenance_date: date
    reported_date: Optional[date] = None
    meter_value: Optional[Decimal] = None
    work_order: Optional[str] = None
    workshop: Optional[str] = None
    technician_id: Optional[int] = None
    status: Optional[str] = None
    is_scheduled: bool = False
    description: Optional[str] = None
    note: Optional[str] = None

    @field_validator("meter_value")
    @classmethod
    def meter_valid(cls, value):
        return _nonnegative(value, "قراءة العداد")

    @model_validator(mode="after")
    def validate_source(self):
        if self.operation_id is None:
            raise ValueError("يجب تحديد عملية الصيانة")
        if self.plan_id is not None and self.operation_id is None:
            raise ValueError("خطة الصيانة لا يمكن ربطها بسجل تنفيذ دون تحديد عملية الصيانة")
        return self


class MaintenancePlanExecutionCreate(BaseModel):
    equipment_id: int
    plan_id: int
    operation_ids: list[int] = Field(min_length=1)
    maintenance_date: date
    meter_value: Optional[Decimal] = None
    reported_date: Optional[date] = None
    work_order: Optional[str] = None
    workshop: Optional[str] = None
    status: Optional[str] = None
    # تنفيذ الخطة يمثل صيانة فعلية مسجلة في سجل العتاد، وليس حجزًا مجدولًا.
    is_scheduled: bool = False
    description: Optional[str] = None

    @field_validator("meter_value")
    @classmethod
    def meter_valid(cls, value):
        return _nonnegative(value, "قراءة العداد")


class MaintenanceRecordOut(MaintenanceRecordCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_by_id: Optional[int] = None
    created_at: object

    # القراءة لا تفرض ما تفرضه الكتابة. سجلات الصيانة القديمة سُجّلت قبل
    # بند «عملية الصيانة»، فبقيت operation_id فارغة فيها. كان هذا الصنف
    # يرث مُتحقّق الإدخال فيُسقط قائمة /api/maintenance/execution كلها
    # بخطأ 500 عند قراءة أي سجل قديم. هنا نُبقي القيمة كما هي (None)
    # ولا نخترع عملية لها،(Input لا يزال محمياً في MaintenanceRecordCreate).
    @model_validator(mode="after")
    def validate_source(self):
        return self
