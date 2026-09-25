from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType, EquipmentModelSpecDefinition, EquipmentModelSpecValue, equipment_type_spec_definitions
from app.modules.tires.models import TirePosition, TireModelSize, TireMovement
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentTypeCreate, EquipmentTypeUpdate, SpecDefinitionCreate, SpecValueInput

def list_categories(db: Session) -> list[EquipmentCategory]: return db.query(EquipmentCategory).order_by(EquipmentCategory.sort_order, EquipmentCategory.name).all()
def list_user_categories(db: Session) -> list[EquipmentCategory]: return db.query(EquipmentCategory).filter(EquipmentCategory.is_system.is_(False)).order_by(EquipmentCategory.sort_order, EquipmentCategory.name).all()
def list_technical_library_categories(db: Session) -> list[EquipmentCategory]: return db.query(EquipmentCategory).filter(EquipmentCategory.is_system.is_(True)).order_by(EquipmentCategory.sort_order, EquipmentCategory.name).all()
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
def delete_brand(db: Session, obj: EquipmentBrand) -> None:
    if db.query(EquipmentModel.id).filter(
        EquipmentModel.brand_id == obj.id
    ).first():
        raise ValueError(
            "لا يمكن حذف علامة تجارية مرتبطة بطرازات؛ "
            "غيّر العلامة التجارية للطرازات أولًا"
        )

    db.delete(obj)
    db.commit()

def set_brand_active(db:Session,obj:EquipmentBrand,active:bool)->EquipmentBrand:
    obj.is_active=active;db.commit();db.refresh(obj);return obj

def list_types(db:Session)->list[EquipmentType]: return db.query(EquipmentType).options(joinedload(EquipmentType.models).joinedload(EquipmentModel.brand),joinedload(EquipmentType.category)).order_by(EquipmentType.name).all()
def list_user_types(db:Session)->list[EquipmentType]: return db.query(EquipmentType).join(EquipmentCategory, EquipmentType.category_id == EquipmentCategory.id, isouter=True).filter((EquipmentCategory.is_system.is_(False)) | (EquipmentType.category_id.is_(None))).options(joinedload(EquipmentType.models).joinedload(EquipmentModel.brand),joinedload(EquipmentType.category),joinedload(EquipmentType.technical_library_type)).order_by(EquipmentType.name).all()
def get_type(db:Session,type_id:int)->Optional[EquipmentType]: return db.query(EquipmentType).options(joinedload(EquipmentType.category)).filter(EquipmentType.id==type_id).first()
def get_type_by_name(db:Session,name:str)->Optional[EquipmentType]: return db.query(EquipmentType).filter(EquipmentType.name==name).first()
def create_type(db:Session,data:EquipmentTypeCreate)->EquipmentType:
    name=data.name.strip()
    if not name: raise ValueError("اسم نوع العتاد مطلوب")
    if get_type_by_name(db,name): raise ValueError("نوع العتاد موجود مسبقًا")
    category=get_category(db,data.category_id)
    if category is None or category.is_system: raise ValueError("اختر فئة المؤسسة الخاصة بك")
    obj=EquipmentType(name=name,measurement_unit=data.measurement_unit,theoretical_quantity=data.theoretical_quantity,category_id=data.category_id);db.add(obj);db.commit();db.refresh(obj);return obj
def update_type(db:Session,obj:EquipmentType,data:EquipmentTypeUpdate)->EquipmentType:
    if obj.is_frozen: raise ValueError("نوع العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل بياناته")
    name=data.name.strip()
    if not name: raise ValueError("اسم نوع العتاد مطلوب")
    category=get_category(db,data.category_id)
    if category is None or category.is_system: raise ValueError("اختر فئة المؤسسة الخاصة بك")
    if db.query(EquipmentType).filter(EquipmentType.id!=obj.id,EquipmentType.name==name).first(): raise ValueError("نوع العتاد موجود مسبقًا")
    if data.measurement_unit != obj.measurement_unit:
        from app.modules.equipment.models import Equipment
        if db.query(Equipment.id).filter(Equipment.equipment_type_id==obj.id).first(): raise ValueError("لا يمكن تغيير وحدة القياس لنوع مرتبط بعتاد فعلي؛ حفاظًا على تاريخ القراءات")
    obj.name=name;obj.measurement_unit=data.measurement_unit;obj.category_id=data.category_id;obj.theoretical_quantity=data.theoretical_quantity;db.commit();db.refresh(obj);return obj
def set_type_category(db:Session,obj:EquipmentType,category_id:int)->EquipmentType:
    if get_category(db,category_id) is None: raise ValueError("فئة العتاد مطلوبة ويجب أن تكون موجودة")
    obj.category_id=category_id;db.commit();db.refresh(obj);return obj
def set_type_theoretical_quantity(db:Session,obj:EquipmentType,quantity:Optional[int])->EquipmentType:
    if quantity is not None and quantity<0: raise ValueError("التعداد النظري لا يمكن أن يكون سالبًا")
    obj.theoretical_quantity=quantity;db.commit();db.refresh(obj);return obj
def set_type_frozen(db:Session,obj:EquipmentType,frozen:bool)->EquipmentType:
    obj.is_frozen=frozen;db.commit();db.refresh(obj);return obj
def delete_type(db:Session,obj:EquipmentType)->None:
    if obj.is_frozen: raise ValueError("نوع العتاد مجمد؛ أعد اعتماده أولًا قبل الحذف")

    from app.modules.equipment.models import Equipment
    from app.modules.maintenance.models import MaintenanceRecord, MaintenanceRule

    # وجود سجل فعلي أو تاريخ تشغيلي في وحدة أخرى يمنع الحذف حفاظًا على التاريخ.
    if db.query(Equipment.id).filter(Equipment.equipment_type_id==obj.id).first():
        raise ValueError("لا يمكن حذف نوع عتاد مستخدم في سجلات العتاد؛ احذف أو انقل السجلات وفق إجراءات النظام أولًا")

    model_ids=[row[0] for row in db.query(EquipmentModel.id).filter(EquipmentModel.equipment_type_id==obj.id).all()]
    if model_ids:
        rule_ids=[row[0] for row in db.query(MaintenanceRule.id).filter(MaintenanceRule.equipment_type_id==obj.id).all()]
        if rule_ids and db.query(MaintenanceRecord.id).filter(MaintenanceRecord.rule_id.in_(rule_ids)).first():
            raise ValueError("لا يمكن حذف نوع عتاد له سجلات صيانة محفوظة؛ حافظ على التاريخ أولًا")
        if db.query(MaintenanceRule.id).filter(MaintenanceRule.equipment_model_id.in_(model_ids)).first():
            raise ValueError("لا يمكن حذف نوع عتاد له قواعد صيانة مسجلة؛ احذف أو انقل قواعد الصيانة وفق إجراءات النظام أولًا")

    db.delete(obj);db.commit()

def list_spec_definitions(db: Session) -> list[EquipmentModelSpecDefinition]:
    return db.query(EquipmentModelSpecDefinition).order_by(
        EquipmentModelSpecDefinition.group_sort_order,
        EquipmentModelSpecDefinition.group_name,
        EquipmentModelSpecDefinition.sort_order,
        EquipmentModelSpecDefinition.name,
    ).all()

def list_spec_definition_type_ids(db: Session) -> dict[int, list[int]]:
    rows = db.execute(
        equipment_type_spec_definitions.select()
    ).fetchall()
    result: dict[int, list[int]] = {}
    for type_id, definition_id in rows:
        result.setdefault(definition_id, []).append(type_id)
    return result

def create_spec_definition(db: Session, data: SpecDefinitionCreate) -> EquipmentModelSpecDefinition:
    name=data.name.strip()
    if not name: raise ValueError("اسم الخاصية مطلوب")
    if db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.name==name).first():
        raise ValueError("توجد خاصية بهذا الاسم مسبقًا")
    code=(data.code or "").strip().lower().replace(" ","_") or None
    if code and db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.code==code).first():
        raise ValueError("رمز الخاصية مستخدم مسبقًا")
    if data.equipment_type_id is not None and get_type(db,data.equipment_type_id) is None:
        raise ValueError("نوع العتاد المحدد للخاصية غير موجود")
    if data.category_id is not None and get_category(db,data.category_id) is None:
        raise ValueError("فئة العتاد المحددة للخاصية غير موجودة")
    options=None
    if data.data_type=="select":
        vals=[o.strip() for o in (data.options or "").split(",") if o.strip()]
        if len(vals)<2: raise ValueError("خاصية من نوع اختيار تحتاج قيمتين على الأقل مفصولتين بفاصلة")
        options=",".join(dict.fromkeys(vals))
    obj=EquipmentModelSpecDefinition(
        name=name, code=code, data_type=data.data_type,
        unit=(data.unit or "").strip() or None, options=options,
        group_name=(data.group_name or "").strip() or "التعريف الفني",
        group_sort_order=max(0,data.group_sort_order),
        equipment_type_id=data.equipment_type_id,
        category_id=data.category_id,
        sort_order=db.query(EquipmentModelSpecDefinition).count(),
    )
    db.add(obj);db.commit();db.refresh(obj);return obj

def delete_spec_definition(db: Session, definition_id: int) -> None:
    obj=db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.id==definition_id).first()
    if obj is not None: db.delete(obj);db.commit()

def list_models(db:Session,type_id:Optional[int]=None)->list[EquipmentModel]:
    query=db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.spec_values).joinedload(EquipmentModelSpecValue.definition),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category))
    if type_id: query=query.filter(EquipmentModel.equipment_type_id==type_id)
    return query.order_by(EquipmentModel.name).all()
def get_model(db:Session,model_id:int)->Optional[EquipmentModel]: return db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.spec_values).joinedload(EquipmentModelSpecValue.definition),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category)).filter(EquipmentModel.id==model_id).first()

def _validate_model_data(db:Session,data:EquipmentModelCreate,obj:EquipmentModel|None=None)->None:
    equipment_type=get_type(db,data.equipment_type_id)
    if equipment_type is None: raise ValueError("نوع العتاد المحدد غير موجود")
    if equipment_type.is_frozen: raise ValueError("نوع العتاد مجمد؛ فك التجميد أولًا قبل إضافة أو نقل الطراز إليه")
    if equipment_type.category_id is None: raise ValueError("لا يمكن إضافة طراز قبل ربط النوع بفئة")
    brand=get_brand(db,data.brand_id) if data.brand_id is not None else None
    if data.brand_id is not None and brand is None: raise ValueError("العلامة التجارية المحددة غير موجودة")
    if brand is not None and not brand.is_active: raise ValueError("العلامة التجارية غير نشطة؛ أعد تفعيلها أولًا")
    if data.has_tires and data.tire_positions_required<1: raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد عدد مواضع الإطارات")
    if data.has_tires and data.axle_count is not None and data.axle_count < 1: raise ValueError("عدد المحاور يجب أن يكون رقمًا موجبًا")
    if not data.has_tires and data.axle_count is not None: raise ValueError("لا يمكن تحديد عدد محاور لطراز غير مزود بالإطارات")
    if not data.has_tires and (data.tire_positions_required!=0 or (data.tire_size or "").strip()): raise ValueError("بيانات الإطارات يجب أن تكون فارغة إذا كان الطراز لا يملك إطارات")
    if data.has_batteries and data.battery_count_required<1: raise ValueError("هذا الطراز يملك بطاريات؛ يجب تحديد عدد البطاريات")
    if data.has_batteries and (data.battery_capacity_ah is None or data.battery_capacity_ah<=0): raise ValueError("يجب تحديد سعة البطارية بالأمبير/ساعة")
    if data.has_batteries and (data.battery_voltage_v is None or data.battery_voltage_v<=0): raise ValueError("يجب تحديد فولط البطارية")
    if not data.has_batteries and (data.battery_count_required!=0 or data.battery_capacity_ah is not None or data.battery_voltage_v is not None): raise ValueError("بيانات البطاريات يجب أن تكون فارغة إذا كان الطراز لا يملك بطاريات")
    name=data.name.strip()
    if not name: raise ValueError("اسم الطراز مطلوب")
    q=db.query(EquipmentModel).filter(EquipmentModel.equipment_type_id==data.equipment_type_id,EquipmentModel.name==name,EquipmentModel.brand_id==data.brand_id)
    if obj is not None: q=q.filter(EquipmentModel.id!=obj.id)
    if q.first(): raise ValueError("الطراز موجود مسبقًا لهذا النوع والعلامة")

def _validate_and_sync_specs(db: Session, equipment_model_id: int, specs: list[SpecValueInput]):
    # Central technical-properties library: category/type applicability is suggestion only.
    definitions={d.id:d for d in db.query(EquipmentModelSpecDefinition).all()}
    seen=set();normalized=[]
    for item in specs:
        if item.definition_id not in definitions:
            raise ValueError("توجد خاصية في النموذج لم تعد معرّفة في مكتبة الخصائص الفنية")
        if item.definition_id in seen:
            raise ValueError("لا يمكن إدخال نفس الخاصية أكثر من مرة لنفس الطراز")
        seen.add(item.definition_id)
        value=(item.value or "").strip()
        if not value: continue
        definition=definitions[item.definition_id]
        if definition.data_type=="number":
            try: float(value)
            except ValueError as exc: raise ValueError(f"قيمة '{definition.name}' يجب أن تكون رقمًا") from exc
        elif definition.data_type=="select":
            allowed={o.strip() for o in (definition.options or "").split(",") if o.strip()}
            if value not in allowed: raise ValueError(f"قيمة '{definition.name}' يجب أن تكون إحدى: {definition.options}")
        normalized.append((item.definition_id,value))
    existing={r.spec_definition_id:r for r in db.query(EquipmentModelSpecValue).filter(EquipmentModelSpecValue.equipment_model_id==equipment_model_id).all()}
    submitted={i for i,_ in normalized}
    for did,row in existing.items():
        if did not in submitted: db.delete(row)
    for did,value in normalized:
        if did in existing: existing[did].value=value
        else: db.add(EquipmentModelSpecValue(equipment_model_id=equipment_model_id,spec_definition_id=did,value=value))

POSITION_SIDES={"left","right"};POSITION_TYPES={"single","inner","outer"}
def _assert_size_deletable(db: Session, equipment_model_id: int, size_value: str) -> None:
    size_key=(size_value or "").strip().lower()
    if not size_key:return
    from app.modules.tires.models import Tire
    from app.modules.tires import state_engine
    for tire in db.query(Tire).filter(Tire.size.isnot(None)).all():
        if (tire.size or "").strip().lower()!=size_key:continue
        movements=db.query(TireMovement).filter(TireMovement.tire_id==tire.id).all()
        if not movements:continue
        state=state_engine.state_from_history(movements)
        if state and state.get("installed"):
            equipment=state.get("equipment");equipment_id=state.get("equipment_id")
            if equipment is None and equipment_id:
                from app.modules.equipment.models import Equipment
                equipment=db.query(Equipment).filter(Equipment.id==equipment_id).first()
            if equipment and equipment.equipment_model_id==equipment_model_id:raise ValueError("لا يمكن حذف مقاس مستخدم على إطار مركب لهذا الطراز")

def _validate_tire_positions_and_sizes(db,data,existing_model_id=None):
    if not data.has_tires:
        if data.positions:raise ValueError("لا يمكن تعريف مواضع إطارات لطراز غير مزود بالإطارات")
        if data.sizes:raise ValueError("لا يمكن تعريف مقاسات معتمدة لطراز غير مزود بالإطارات")
        if existing_model_id is not None:
            old_position_ids={row[0] for row in db.query(TirePosition.id).filter(TirePosition.equipment_model_id==existing_model_id).all()}
            if old_position_ids and db.query(TireMovement.id).filter(TireMovement.position_id.in_(old_position_ids)).first():raise ValueError("لا يمكن حذف موضع استُخدم في سجل حركات؛ حافظ على التاريخ")
            for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==existing_model_id).all():_assert_size_deletable(db,existing_model_id,row.size)
        return
    if len(data.positions)!=data.tire_positions_required:raise ValueError(f"يجب تعريف {data.tire_positions_required} موضع إطار بالضبط قبل حفظ الطراز (المعرَّف حاليًا في النموذج: {len(data.positions)})")
    seen=set()
    for p in data.positions:
        key=(p.axle_number,p.side,p.position_type)
        if key in seen:raise ValueError("توجد مواضع مكررة بنفس المحور والجهة والنوع")
        seen.add(key)
    if data.axle_count is not None:
        invalid=[p.axle_number for p in data.positions if p.axle_number > data.axle_count]
        if invalid:
            raise ValueError(f"رقم المحور {max(invalid)} يتجاوز عدد محاور الطراز المحدد ({data.axle_count})")
    existing_ids=set();existing_sizes={}
    if existing_model_id is not None:
        existing_ids={row[0] for row in db.query(TirePosition.id).filter(TirePosition.equipment_model_id==existing_model_id).all()}
        submitted_ids={p.id for p in data.positions if p.id is not None}
        if submitted_ids-existing_ids:raise ValueError("توجد مواضع في النموذج لا تنتمي لهذا الطراز")
        to_delete=existing_ids-submitted_ids
        if to_delete and db.query(TireMovement.id).filter(TireMovement.position_id.in_(to_delete)).first():raise ValueError("لا يمكن حذف موضع استُخدم في سجل حركات؛ حافظ على التاريخ")
        existing_sizes={row.id:row.size for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==existing_model_id).all()}
    normalized=[];seen_sizes=set()
    for raw in data.sizes:
        value=(raw or "").strip()
        if not value:continue
        key=value.lower()
        if key in seen_sizes:raise ValueError(f"المقاس مكرر: {value}")
        seen_sizes.add(key);normalized.append(value)
    if not (data.tire_size or "").strip() and not normalized:raise ValueError("هذا الطراز يملك إطارات؛ يجب تحديد المقاس الافتراضي أو إضافة مقاس معتمد واحد على الأقل")
    if existing_model_id is not None:
        submitted_norm={v.lower() for v in normalized}
        for size_id,size_value in existing_sizes.items():
            if (size_value or "").strip().lower() not in submitted_norm:_assert_size_deletable(db,existing_model_id,size_value)

def _sync_positions(db,equipment_model_id,positions):
    existing={p.id:p for p in db.query(TirePosition).filter(TirePosition.equipment_model_id==equipment_model_id).all()};submitted_ids={p.id for p in positions if p.id is not None}
    for pid,obj in existing.items():
        if pid not in submitted_ids:db.delete(obj)
    names={"left":"يسار","right":"يمين"};types={"single":"مفرد","inner":"داخلي","outer":"خارجي"}
    for p in positions:
        if p.id is not None:
            obj=existing[p.id];obj.axle_number=p.axle_number;obj.side=p.side;obj.position_type=p.position_type;obj.name=f"المحور {p.axle_number} — {names[p.side]} {types[p.position_type]}";obj.code=f"M{equipment_model_id}-A{p.axle_number}-{p.side}-{p.position_type}";obj.description=(p.description or "").strip() or None;obj.sort_order=p.axle_number
        else:db.add(TirePosition(equipment_model_id=equipment_model_id,axle_number=p.axle_number,side=p.side,position_type=p.position_type,code=f"M{equipment_model_id}-A{p.axle_number}-{p.side}-{p.position_type}",name=f"المحور {p.axle_number} — {names[p.side]} {types[p.position_type]}",description=(p.description or "").strip() or None,sort_order=p.axle_number))

def _sync_sizes(db,equipment_model_id,tire_size,sizes):
    existing={row.size.strip().lower():row for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==equipment_model_id).all() if row.size};normalized=[]
    for raw in sizes:
        value=(raw or "").strip()
        if value and value.lower() not in {v.lower() for v in normalized}:normalized.append(value)
    submitted={v.lower() for v in normalized}
    for key,row in existing.items():
        if key not in submitted:db.delete(row)
    for value in normalized:
        if value.lower() not in existing:db.add(TireModelSize(equipment_model_id=equipment_model_id,size=value))

def add_model_size(db:Session,equipment_model_id:int,size:str):
    value=(size or "").strip()
    if not value:raise ValueError("مقاس الإطار مطلوب")
    model=db.query(EquipmentModel).filter(EquipmentModel.id==equipment_model_id).first()
    if not model:raise ValueError("الطراز غير موجود")
    if db.query(TireModelSize.id).filter(TireModelSize.equipment_model_id==equipment_model_id,TireModelSize.size.ilike(value)).first():raise ValueError("المقاس موجود مسبقًا لهذا الطراز")
    obj=TireModelSize(equipment_model_id=equipment_model_id,size=value);db.add(obj);db.commit();db.refresh(obj);return obj

def delete_model_size(db:Session,size_id:int):
    obj=db.query(TireModelSize).filter(TireModelSize.id==size_id).first()
    if obj is None:raise ValueError("المقاس غير موجود")
    _assert_size_deletable(db,obj.equipment_model_id,obj.size);db.delete(obj);db.commit()

def add_position(db:Session,equipment_model_id:int,axle_number:int,side:str,position_type:str,description:str=""):
    if side not in POSITION_SIDES:raise ValueError("جهة الموضع غير صالحة")
    if position_type not in POSITION_TYPES:raise ValueError("نوع الموضع غير صالح")
    if axle_number<1:raise ValueError("رقم المحور غير صالح")
    if db.query(TirePosition.id).filter(TirePosition.equipment_model_id==equipment_model_id,TirePosition.axle_number==axle_number,TirePosition.side==side,TirePosition.position_type==position_type).first():raise ValueError("الموضع موجود مسبقًا")
    name_side="يسار" if side=="left" else "يمين";name_type={"single":"مفرد","inner":"داخلي","outer":"خارجي"}[position_type]
    obj=TirePosition(equipment_model_id=equipment_model_id,axle_number=axle_number,side=side,position_type=position_type,code=f"M{equipment_model_id}-A{axle_number}-{side}-{position_type}",name=f"المحور {axle_number} — {name_side} {name_type}",description=(description or "").strip() or None,sort_order=axle_number);db.add(obj);db.commit();db.refresh(obj);return obj

def delete_position(db:Session,position_id:int):
    obj=db.query(TirePosition).filter(TirePosition.id==position_id).first()
    if obj is None:raise ValueError("الموضع غير موجود")
    if db.query(TireMovement.id).filter(TireMovement.position_id==position_id).first():raise ValueError("لا يمكن حذف موضع استُخدم في سجل حركات؛ حافظ على التاريخ")
    db.delete(obj);db.commit()

def create_model(db:Session,data:EquipmentModelCreate)->EquipmentModel:
    _validate_model_data(db,data);_validate_tire_positions_and_sizes(db,data,None)
    obj=EquipmentModel(name=data.name.strip(),equipment_type_id=data.equipment_type_id,brand_id=data.brand_id,has_tires=data.has_tires,tire_positions_required=data.tire_positions_required,axle_count=data.axle_count,tire_size=(data.tire_size or "").strip() or None,has_batteries=data.has_batteries,battery_count_required=data.battery_count_required,battery_capacity_ah=data.battery_capacity_ah,battery_voltage_v=data.battery_voltage_v,mobility_type=data.mobility_type,requires_driver=data.requires_driver)
    db.add(obj);db.flush();_sync_positions(db,obj.id,[p.model_copy(update={"id":None}) for p in data.positions] if data.has_tires else []);_sync_sizes(db,obj.id,data.tire_size,data.sizes if data.has_tires else []);db.flush();_validate_and_sync_specs(db,obj.id,data.specs)
    db.commit();db.refresh(obj);return obj

def update_model(db:Session,obj:EquipmentModel,data:EquipmentModelCreate)->EquipmentModel:
    if obj.is_frozen:raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل تعديل بياناته")
    _validate_model_data(db,data,obj=obj);_validate_tire_positions_and_sizes(db,data,obj.id)
    if data.equipment_type_id!=obj.equipment_type_id:
        from app.modules.equipment.models import Equipment
        if db.query(Equipment.id).filter(Equipment.equipment_model_id==obj.id).first():raise ValueError("لا يمكن نقل طراز مرتبط بعتاد فعلي إلى نوع آخر؛ حافظ على التاريخ والمرجع")
    obj.name=data.name.strip();obj.equipment_type_id=data.equipment_type_id;obj.brand_id=data.brand_id;obj.has_tires=data.has_tires;obj.tire_positions_required=data.tire_positions_required;obj.axle_count=data.axle_count;obj.tire_size=(data.tire_size or "").strip() or None;obj.has_batteries=data.has_batteries;obj.battery_count_required=data.battery_count_required;obj.battery_capacity_ah=data.battery_capacity_ah;obj.battery_voltage_v=data.battery_voltage_v;obj.mobility_type=data.mobility_type;obj.requires_driver=data.requires_driver
    _sync_positions(db,obj.id,data.positions if data.has_tires else []);_sync_sizes(db,obj.id,data.tire_size,data.sizes if data.has_tires else []);db.flush();_validate_and_sync_specs(db,obj.id,data.specs)
    db.commit();db.refresh(obj);return obj

def move_model_to_type(db:Session,obj:EquipmentModel,equipment_type_id:int)->EquipmentModel:
    if obj.is_frozen: raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل نقله")
    target=db.query(EquipmentType).filter(EquipmentType.id==equipment_type_id).first()
    if target is None: raise ValueError("نوع العتاد الهدف غير موجود")
    if obj.equipment_type_id==target.id: return obj
    from app.modules.equipment.models import Equipment
    if db.query(Equipment.id).filter(Equipment.equipment_model_id==obj.id).first():
        raise ValueError("لا يمكن نقل طراز مرتبط بعتاد فعلي إلى نوع آخر؛ حافظ على التاريخ والمرجع")
    duplicate=db.query(EquipmentModel).filter(EquipmentModel.id!=obj.id,EquipmentModel.equipment_type_id==target.id,EquipmentModel.brand_id==obj.brand_id,EquipmentModel.name==obj.name).first()
    if duplicate: raise ValueError("يوجد طراز بالاسم نفسه للعلامة التجارية داخل نوع العتاد الهدف")
    obj.equipment_type_id=target.id;db.commit();db.refresh(obj);return obj

def set_model_brand(db:Session,obj:EquipmentModel,brand_id:int)->EquipmentModel:
    brand=get_brand(db,brand_id)
    if brand is None or not brand.is_active:raise ValueError("العلامة التجارية غير موجودة أو غير نشطة")
    duplicate=db.query(EquipmentModel).filter(EquipmentModel.id!=obj.id,EquipmentModel.equipment_type_id==obj.equipment_type_id,EquipmentModel.brand_id==brand_id,EquipmentModel.name==obj.name).first()
    if duplicate:raise ValueError("يوجد طراز بالاسم نفسه لهذا النوع والعلامة")
    obj.brand_id=brand_id;db.commit();db.refresh(obj);return obj

def set_model_frozen(db:Session,obj:EquipmentModel,frozen:bool)->EquipmentModel:
    obj.is_frozen=frozen;db.commit();db.refresh(obj);return obj

def delete_model(db:Session,obj:EquipmentModel)->None:
    from app.modules.equipment.models import Equipment
    from app.modules.tires.models import TireModelSize,TirePosition
    if obj.is_frozen:raise ValueError("طراز العتاد مجمد؛ أعد اعتماده أولًا قبل الحذف")
    if db.query(Equipment.id).filter(Equipment.equipment_model_id==obj.id).first():raise ValueError("لا يمكن حذف طراز مرتبط بعتاد مسجل؛ غيّر ارتباط العتاد أو احذف السجل وفق إجراءات النظام أولًا")
    # إعدادات الإطارات جزء من بيانات الطراز المرجعية، لذلك تُزال معه.
    # حركات الإطارات التاريخية لا تُحذف؛ position_id فيها يتحول إلى NULL بسبب FK SET NULL.
    db.query(TireModelSize).filter(TireModelSize.equipment_model_id==obj.id).delete(synchronize_session=False)
    db.query(TirePosition).filter(TirePosition.equipment_model_id==obj.id).delete(synchronize_session=False)
    db.delete(obj);db.commit()