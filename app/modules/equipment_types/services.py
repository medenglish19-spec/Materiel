from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentTypeCreate, EquipmentTypeUpdate

def list_categories(db: Session) -> list[EquipmentCategory]: return db.query(EquipmentCategory).order_by(EquipmentCategory.sort_order, EquipmentCategory.name).all()
def get_category(db: Session, category_id: int) -> Optional[EquipmentCategory]: return db.query(EquipmentCategory).filter(EquipmentCategory.id == category_id).first()
def create_category(db: Session, data: EquipmentCategoryCreate) -> EquipmentCategory:
    name=data.name.strip()
    if not name: raise ValueError("اسم الفئة مطلوب")
    if get_category_by_name(db,name): raise ValueError("الفئة موجودة مسبقًا")
    code=(data.code or name).strip().lower().replace(" ","-")[:30] or f"category-{db.query(EquipmentCategory).count()+1}"
    if db.query(EquipmentCategory).filter(EquipmentCategory.code==code).first(): code=f"{code}-{db.query(EquipmentCategory).count()+1}"[:30]
    obj=EquipmentCategory(name=name,code=code,is_system=False);db.add(obj);db.commit();db.refresh(obj);return obj
def get_category_by_name(db: Session,name:str)->Optional[EquipmentCategory]: return db.query(EquipmentCategory).filter(EquipmentCategory.name==name).first()
def update_category(db:Session,obj:EquipmentCategory,data:EquipmentCategoryUpdate)->EquipmentCategory:
    name=data.name.strip()
    if not name: raise ValueError("اسم الفئة مطلوب")
    if db.query(EquipmentCategory).filter(EquipmentCategory.id!=obj.id,EquipmentCategory.name==name).first(): raise ValueError("الفئة موجودة مسبقًا")
    code=(data.code or name).strip().lower().replace(" ","-")[:30]
    if db.query(EquipmentCategory).filter(EquipmentCategory.id!=obj.id,EquipmentCategory.code==code).first(): raise ValueError("رمز الفئة مستخدم مسبقًا")
    obj.name=name;obj.code=code;db.commit();db.refresh(obj);return obj
def delete_category(db:Session,obj:EquipmentCategory)->None:
    if obj.is_system: raise ValueError("الفئات الأساسية للنظام لا يمكن حذفها")
    if db.query(EquipmentType.id).filter(EquipmentType.category_id==obj.id).first(): raise ValueError("لا يمكن حذف فئة مرتبطة بأنواع عتاد؛ انقل الأنواع إلى فئة أخرى أولًا")
    db.delete(obj);db.commit()

def create_demo_classification(db: Session) -> None:
    category_name="مثال: مركبات";type_name="مثال: مركبات خفيفة";brand_name="مثال: Toyota";model_name="مثال: Land Cruiser"
    category=db.query(EquipmentCategory).filter(EquipmentCategory.name==category_name).first()
    if category is None: category=EquipmentCategory(name=category_name,code=f"demo-vehicles-{db.query(EquipmentCategory).count()+1}",is_system=False);db.add(category);db.flush()
    brand=db.query(EquipmentBrand).filter(EquipmentBrand.name==brand_name).first()
    if brand is None: brand=EquipmentBrand(name=brand_name,is_active=True);db.add(brand);db.flush()
    equipment_type=db.query(EquipmentType).filter(EquipmentType.name==type_name).first()
    if equipment_type is None: equipment_type=EquipmentType(name=type_name,measurement_unit="km",theoretical_quantity=1,category_id=category.id);db.add(equipment_type);db.flush()
    model=db.query(EquipmentModel).filter(EquipmentModel.equipment_type_id==equipment_type.id,EquipmentModel.name==model_name).first()
    if model is None: db.add(EquipmentModel(name=model_name,equipment_type_id=equipment_type.id,brand_id=brand.id,mobility_type="mobile",requires_driver=True))
    db.commit()

def list_brands(db:Session, active_only: bool = False)->list[EquipmentBrand]:
    query=db.query(EquipmentBrand)
    if active_only: query=query.filter(EquipmentBrand.is_active.is_(True))
    return query.order_by(EquipmentBrand.name).all()
def get_brand(db:Session,brand_id:int)->Optional[EquipmentBrand]: return db.query(EquipmentBrand).filter(EquipmentBrand.id == brand_id).first()
def create_brand(db:Session,data:EquipmentBrandCreate)->EquipmentBrand:
    name=data.name.strip()
    if not name: raise ValueError("اسم العلامة التجارية مطلوب")
    if db.query(EquipmentBrand).filter(EquipmentBrand.name==name).first(): raise ValueError("العلامة التجارية موجودة مسبقًا")
    obj=EquipmentBrand(name=name);db.add(obj);db.commit();db.refresh(obj);return obj
def update_brand(db:Session,obj:EquipmentBrand,data:EquipmentBrandUpdate)->EquipmentBrand:
    name=data.name.strip()
    if not name: raise ValueError("اسم العلامة التجارية مطلوب")
    if db.query(EquipmentBrand).filter(EquipmentBrand.id!=obj.id,EquipmentBrand.name==name).first(): raise ValueError("العلامة التجارية موجودة مسبقًا")
    obj.name=name;db.commit();db.refresh(obj);return obj
def set_brand_active(db:Session,obj:EquipmentBrand,active:bool)->EquipmentBrand:
    obj.is_active=active;db.commit();db.refresh(obj);return obj

def list_types(db:Session)->list[EquipmentType]: return db.query(EquipmentType).options(joinedload(EquipmentType.models).joinedload(EquipmentModel.brand),joinedload(EquipmentType.category)).order_by(EquipmentType.name).all()
def get_type(db:Session,type_id:int)->Optional[EquipmentType]: return db.query(EquipmentType).options(joinedload(EquipmentType.category)).filter(EquipmentType.id==type_id).first()
def get_type_by_name(db:Session,name:str)->Optional[EquipmentType]: return db.query(EquipmentType).filter(EquipmentType.name==name).first()
def create_type(db:Session,data:EquipmentTypeCreate)->EquipmentType:
    name=data.name.strip()
    if not name: raise ValueError("اسم نوع العتاد مطلوب")
    if get_type_by_name(db,name): raise ValueError("نوع العتاد موجود مسبقًا")
    category=get_category(db,data.category_id)
    if category is None: raise ValueError("فئة العتاد مطلوبة ويجب أن تكون موجودة")
    if category.is_system is False and not category.name.strip(): raise ValueError("فئة العتاد غير صالحة")
    obj=EquipmentType(name=name,measurement_unit=data.measurement_unit,theoretical_quantity=data.theoretical_quantity,category_id=data.category_id);db.add(obj);db.commit();db.refresh(obj);return obj
def update_type(db:Session,obj:EquipmentType,data:EquipmentTypeUpdate)->EquipmentType:
    if obj.is_frozen: raise ValueError("نوع العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل بياناته")
    name=data.name.strip()
    if not name: raise ValueError("اسم نوع العتاد مطلوب")
    if get_category(db,data.category_id) is None: raise ValueError("فئة العتاد مطلوبة ويجب أن تكون موجودة")
    if db.query(EquipmentType).filter(EquipmentType.id!=obj.id,EquipmentType.name==name).first(): raise ValueError("نوع العتاد موجود مسبقًا")
    if data.measurement_unit != obj.measurement_unit:
        from app.modules.equipment.models import Equipment
        if db.query(Equipment.id).filter(Equipment.equipment_type_id==obj.id).first(): raise ValueError("لا يمكن تغيير وحدة القياس لنوع مرتبط بعتاد فعلي؛ حفاظًا على تاريخ القراءات")
    obj.name=name;obj.measurement_unit=data.measurement_unit;obj.category_id=data.category_id;obj.theoretical_quantity=data.theoretical_quantity;db.commit();db.refresh(obj);return obj
def set_type_category(db:Session,obj:EquipmentType,category_id:int)->EquipmentType:
    if obj.is_frozen: raise ValueError("نوع العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل الفئة")
    if get_category(db,category_id) is None: raise ValueError("فئة العتاد مطلوبة ويجب أن تكون موجودة")
    obj.category_id=category_id;db.commit();db.refresh(obj);return obj
def set_type_theoretical_quantity(db:Session,obj:EquipmentType,quantity:Optional[int])->EquipmentType:
    if obj.is_frozen: raise ValueError("نوع العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل التعداد النظري")
    if quantity is not None and quantity<0: raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
    obj.theoretical_quantity=quantity;db.commit();db.refresh(obj);return obj
def set_type_frozen(db:Session,obj:EquipmentType,frozen:bool)->EquipmentType:
    obj.is_frozen=frozen;db.commit();db.refresh(obj);return obj
def delete_type(db:Session,obj:EquipmentType)->None:
    if obj.is_frozen: raise ValueError("نوع العتاد مجمد؛ أعد اعتماده أولًا قبل الحذف")
    if db.query(EquipmentModel.id).filter(EquipmentModel.equipment_type_id==obj.id).first(): raise ValueError("لا يمكن حذف نوع عتاد مرتبط بطرازات مسجلة؛ احذف أو انقل الطرازات وفق إجراءات النظام أولًا")
    db.delete(obj);db.commit()

def list_models(db:Session,type_id:Optional[int]=None)->list[EquipmentModel]:
    query=db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category))
    if type_id: query=query.filter(EquipmentModel.equipment_type_id==type_id)
    return query.order_by(EquipmentModel.name).all()
def get_model(db:Session,model_id:int)->Optional[EquipmentModel]: return db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category)).filter(EquipmentModel.id==model_id).first()

def _validate_model_data(db:Session,data:EquipmentModelCreate,obj:EquipmentModel|None=None)->None:
    equipment_type=get_type(db,data.equipment_type_id)
    if equipment_type is None: raise ValueError("نوع العتاد المحدد غير موجود")
    if equipment_type.is_frozen: raise ValueError("نوع العتاد مجمد؛ فك التجميد أولًا قبل إضافة أو نقل الطراز إليه")
    if equipment_type.category_id is None: raise ValueError("لا يمكن إضافة طراز قبل ربط النوع بفئة")
    brand=get_brand(db,data.brand_id)
    if brand is None: raise ValueError("العلامة التجارية مطلوبة ويجب أن تكون موجودة")
    if not brand.is_active: raise ValueError("العلامة التجارية غير نشطة؛ أعد تفعيلها أولًا")
    if data.has_tires and data.tire_positions_required<1: raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد عدد مواضع الإطارات")
    if data.has_tires and not (data.tire_size or "").strip(): raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد مقاس الإطار")
    if not data.has_tires and (data.tire_positions_required!=0 or data.tire_size): raise ValueError("بيانات الإطارات يجب أن تكون فارغة إذا كان الطراز لا يملك إطارات")
    if data.has_batteries and data.battery_count_required<1: raise ValueError("هذا الطراز يملك بطاريات؛ يجب تحديد عدد البطاريات")
    if data.has_batteries and (data.battery_capacity_ah is None or data.battery_capacity_ah<=0): raise ValueError("يجب تحديد سعة البطارية بالأمبير/ساعة")
    if data.has_batteries and (data.battery_voltage_v is None or data.battery_voltage_v<=0): raise ValueError("يجب تحديد فولط البطارية")
    if not data.has_batteries and (data.battery_count_required!=0 or data.battery_capacity_ah is not None or data.battery_voltage_v is not None): raise ValueError("بيانات البطاريات يجب أن تكون فارغة إذا كان الطراز لا يملك بطاريات")
    name=data.name.strip()
    if not name: raise ValueError("اسم الطراز مطلوب")
    q=db.query(EquipmentModel).filter(EquipmentModel.equipment_type_id==data.equipment_type_id,EquipmentModel.name==name,EquipmentModel.brand_id==data.brand_id)
    if obj is not None: q=q.filter(EquipmentModel.id!=obj.id)
    if q.first(): raise ValueError("الطراز موجود مسبقًا لهذا النوع والعلامة")

def create_model(db:Session,data:EquipmentModelCreate)->EquipmentModel:
    _validate_model_data(db,data)
    obj=EquipmentModel(name=data.name.strip(),equipment_type_id=data.equipment_type_id,brand_id=data.brand_id,has_tires=data.has_tires,tire_positions_required=data.tire_positions_required,tire_size=(data.tire_size or "").strip() or None,has_batteries=data.has_batteries,battery_count_required=data.battery_count_required,battery_capacity_ah=data.battery_capacity_ah,battery_voltage_v=data.battery_voltage_v,mobility_type=data.mobility_type,requires_driver=data.requires_driver);db.add(obj);db.commit();db.refresh(obj);return obj

def update_model(db:Session,obj:EquipmentModel,data:EquipmentModelCreate)->EquipmentModel:
    if obj.is_frozen: raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل بياناته")
    _validate_model_data(db,data,obj=obj)
    if data.equipment_type_id != obj.equipment_type_id:
        from app.modules.equipment.models import Equipment
        if db.query(Equipment.id).filter(Equipment.equipment_model_id==obj.id).first(): raise ValueError("لا يمكن نقل طراز مرتبط بعتاد فعلي إلى نوع آخر؛ حافظ على التاريخ والمرجع")
    obj.name=data.name.strip();obj.equipment_type_id=data.equipment_type_id;obj.brand_id=data.brand_id;obj.has_tires=data.has_tires;obj.tire_positions_required=data.tire_positions_required;obj.tire_size=(data.tire_size or "").strip() or None;obj.has_batteries=data.has_batteries;obj.battery_count_required=data.battery_count_required;obj.battery_capacity_ah=data.battery_capacity_ah;obj.battery_voltage_v=data.battery_voltage_v;obj.mobility_type=data.mobility_type;obj.requires_driver=data.requires_driver;db.commit();db.refresh(obj);return obj

def set_model_brand(db:Session,obj:EquipmentModel,brand_id:int)->EquipmentModel:
    if obj.is_frozen: raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل العلامة التجارية")
    brand=get_brand(db,brand_id)
    if brand is None or not brand.is_active: raise ValueError("العلامة التجارية غير موجودة أو غير نشطة")
    duplicate=db.query(EquipmentModel).filter(EquipmentModel.id!=obj.id,EquipmentModel.equipment_type_id==obj.equipment_type_id,EquipmentModel.brand_id==brand_id,EquipmentModel.name==obj.name).first()
    if duplicate: raise ValueError("يوجد طراز بالاسم نفسه لهذا النوع والعلامة")
    obj.brand_id=brand_id;db.commit();db.refresh(obj);return obj

def update_model_tire_configuration(db:Session,obj:EquipmentModel,has_tires:bool,tire_positions_required:int,tire_size:str|None)->EquipmentModel:
    if obj.is_frozen: raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل إعدادات الإطارات")
    if tire_positions_required<0: raise ValueError("عدد مواضع الإطارات لا يمكن أن يكون سالبًا")
    normalized_size=(tire_size or "").strip() or None
    from app.modules.tires.models import TirePosition
    configured_count=db.query(TirePosition).filter(TirePosition.equipment_model_id==obj.id).count()
    if not has_tires and configured_count: raise ValueError("لا يمكن تعطيل الإطارات بينما توجد مواضع إطارات معرفة لهذا الطراز؛ احذف المواضع أولًا للحفاظ على اتساق الإعدادات")
    if has_tires and tire_positions_required<1: raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد عدد مواضع الإطارات")
    if has_tires and tire_positions_required<configured_count: raise ValueError(f"عدد مواضع الإطارات المطلوب ({tire_positions_required}) لا يمكن أن يكون أقل من المواضع المعرفة حاليًا ({configured_count})")
    if has_tires and not normalized_size:
        from app.modules.tires.models import TireModelSize
        if not db.query(TireModelSize).filter(TireModelSize.equipment_model_id==obj.id).first(): raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد المقاس الافتراضي أو إضافة مقاس معتمد")
    if not has_tires and (tire_positions_required!=0 or normalized_size is not None): raise ValueError("بيانات الإطارات يجب أن تكون فارغة إذا كان الطراز لا يملك إطارات")
    obj.has_tires=has_tires;obj.tire_positions_required=tire_positions_required;obj.tire_size=normalized_size;db.commit();db.refresh(obj);return obj

def set_model_frozen(db:Session,obj:EquipmentModel,frozen:bool)->EquipmentModel:
    obj.is_frozen=frozen;db.commit();db.refresh(obj);return obj

def delete_model(db:Session,obj:EquipmentModel)->None:
    from app.modules.equipment.models import Equipment
    from app.modules.tires.models import TireModelSize, TirePosition
    if obj.is_frozen: raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل الحذف")
    if db.query(Equipment.id).filter(Equipment.equipment_model_id==obj.id).first(): raise ValueError("لا يمكن حذف طراز مرتبط بعتاد مسجل؛ غيّر ارتباط العتاد أو احذف السجل وفق إجراءات النظام أولًا")
    if db.query(TirePosition.id).filter(TirePosition.equipment_model_id==obj.id).first() or db.query(TireModelSize.id).filter(TireModelSize.equipment_model_id==obj.id).first(): raise ValueError("لا يمكن حذف طراز يحتوي على إعدادات إطارات؛ احذف الإعدادات المرجعية أولًا")
    db.delete(obj);db.commit()