from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"missing replacement anchor: {label}")
    return text.replace(old, new, 1)

# models.py
p="app/modules/equipment_types/models.py"; s=read(p)
s=replace_once(s,
'''    requires_driver = Column(Boolean, nullable=False, default=True)\n    equipment_type = relationship("EquipmentType", back_populates="models")''',
'''    requires_driver = Column(Boolean, nullable=False, default=True)\n    equipment_type = relationship("EquipmentType", back_populates="models")\n    spec_values = relationship("EquipmentModelSpecValue", back_populates="model", cascade="all, delete-orphan")''',
"model relationship")
s += '''\n\nclass EquipmentModelSpecDefinition(Base, TimestampMixin):\n    __tablename__ = "equipment_model_spec_definitions"\n    id = Column(Integer, primary_key=True, index=True)\n    name = Column(String(100), unique=True, nullable=False)\n    data_type = Column(String(20), nullable=False, default="text")\n    unit = Column(String(20), nullable=True)\n    options = Column(String(500), nullable=True)\n    sort_order = Column(Integer, nullable=False, default=0)\n    values = relationship("EquipmentModelSpecValue", back_populates="definition", cascade="all, delete-orphan")\n\n\nclass EquipmentModelSpecValue(Base, TimestampMixin):\n    __tablename__ = "equipment_model_spec_values"\n    __table_args__ = (UniqueConstraint("equipment_model_id", "spec_definition_id", name="uq_model_spec_value"),)\n    id = Column(Integer, primary_key=True, index=True)\n    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=False, index=True)\n    spec_definition_id = Column(Integer, ForeignKey("equipment_model_spec_definitions.id", ondelete="CASCADE"), nullable=False, index=True)\n    value = Column(String(255), nullable=False)\n    definition = relationship("EquipmentModelSpecDefinition", back_populates="values")\n    model = relationship("EquipmentModel", back_populates="spec_values")\n'''
write(p,s)

# schemas.py
p="app/modules/equipment_types/schemas.py"; s=read(p)
s=replace_once(s,'MOBILITY_TYPES = {"mobile", "towed"}\n','MOBILITY_TYPES = {"mobile", "towed"}\nSPEC_DATA_TYPES = {"text", "number", "select"}\n',"spec constants")
anchor='class EquipmentModelCreate(BaseModel):\n'
insert='''class SpecDefinitionCreate(BaseModel):\n    name: str\n    data_type: str = "text"\n    unit: Optional[str] = None\n    options: Optional[str] = None\n    @field_validator("data_type")\n    @classmethod\n    def data_type_valid(cls, v: str) -> str:\n        if v not in SPEC_DATA_TYPES:\n            raise ValueError(f"نوع الخاصية يجب أن يكون أحد: {SPEC_DATA_TYPES}")\n        return v\n\nclass SpecDefinitionOut(BaseModel):\n    model_config = ConfigDict(from_attributes=True)\n    id: int\n    name: str\n    data_type: str\n    unit: Optional[str]\n    options: Optional[str]\n    sort_order: int\n\nclass SpecValueInput(BaseModel):\n    definition_id: int\n    value: str\n\n'''
s=replace_once(s,anchor,insert+anchor,"spec schemas")
s=replace_once(s,'    sizes: list[str] = Field(default_factory=list)\n','    sizes: list[str] = Field(default_factory=list)\n    specs: list[SpecValueInput] = Field(default_factory=list)\n',"model specs")
write(p,s)

# services.py
p="app/modules/equipment_types/services.py"; s=read(p)
s=replace_once(s,
'from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType',
'from app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentType, EquipmentModelSpecDefinition, EquipmentModelSpecValue',
"service model imports")
s=replace_once(s,
'from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentTypeCreate, EquipmentTypeUpdate',
'from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentTypeCreate, EquipmentTypeUpdate, SpecDefinitionCreate, SpecValueInput',
"service schema imports")
s=replace_once(s,
'def list_models(db:Session,type_id:Optional[int]=None)->list[EquipmentModel]:\n    query=db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category))',
'''def list_spec_definitions(db: Session) -> list[EquipmentModelSpecDefinition]:\n    return db.query(EquipmentModelSpecDefinition).order_by(EquipmentModelSpecDefinition.sort_order, EquipmentModelSpecDefinition.name).all()\n\ndef create_spec_definition(db: Session, data: SpecDefinitionCreate) -> EquipmentModelSpecDefinition:\n    name=data.name.strip()\n    if not name: raise ValueError("اسم الخاصية مطلوب")\n    if db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.name==name).first(): raise ValueError("توجد خاصية بهذا الاسم مسبقًا")\n    options=None\n    if data.data_type=="select":\n        options_list=[o.strip() for o in (data.options or "").split(",") if o.strip()]\n        if len(options_list)<2: raise ValueError("خاصية من نوع اختيار تحتاج قيمتين على الأقل مفصولتين بفاصلة")\n        options=",".join(options_list)\n    obj=EquipmentModelSpecDefinition(name=name,data_type=data.data_type,unit=(data.unit or "").strip() or None,options=options,sort_order=db.query(EquipmentModelSpecDefinition).count())\n    db.add(obj);db.commit();db.refresh(obj);return obj\n\ndef delete_spec_definition(db: Session, definition_id: int) -> None:\n    obj=db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.id==definition_id).first()\n    if not obj:return\n    db.delete(obj);db.commit()\n\ndef list_models(db:Session,type_id:Optional[int]=None)->list[EquipmentModel]:\n    query=db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.spec_values).joinedload(EquipmentModelSpecValue.definition),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category))''',
"service model listing")
s=replace_once(s,
'def get_model(db:Session,model_id:int)->Optional[EquipmentModel]: return db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category)).filter(EquipmentModel.id==model_id).first()',
'def get_model(db:Session,model_id:int)->Optional[EquipmentModel]: return db.query(EquipmentModel).options(joinedload(EquipmentModel.brand),joinedload(EquipmentModel.spec_values).joinedload(EquipmentModelSpecValue.definition),joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category)).filter(EquipmentModel.id==model_id).first()',
"service get model")
s=replace_once(s,
'    if not data.has_tires and data.axle_count is not None: raise ValueError("لا يمكن تحديد عدد محاور لطراز غير مزود بالإطارات")\n',
'    if not data.has_tires and data.axle_count is not None: raise ValueError("لا يمكن تحديد عدد محاور لطراز غير مزود بالإطارات")\n',
"axle anchor")
needle='''POSITION_SIDES={"left","right"};POSITION_TYPES={"single","inner","outer"}\n'''
specfunc='''def _validate_and_sync_specs(db: Session, equipment_model_id: int, specs: list[SpecValueInput]):\n    definitions={d.id:d for d in db.query(EquipmentModelSpecDefinition).all()}\n    seen=set();normalized=[]\n    for item in specs:\n        if item.definition_id not in definitions: raise ValueError("توجد خاصية في النموذج لم تعد معرّفة في النظام")\n        if item.definition_id in seen: raise ValueError("لا يمكن إدخال نفس الخاصية أكثر من مرة لنفس الطراز")\n        seen.add(item.definition_id)\n        value=(item.value or "").strip()\n        if not value: continue\n        definition=definitions[item.definition_id]\n        if definition.data_type=="number":\n            try: float(value)\n            except ValueError as exc: raise ValueError(f"قيمة '{definition.name}' يجب أن تكون رقمًا") from exc\n        elif definition.data_type=="select":\n            allowed={o.strip() for o in (definition.options or "").split(",")}\n            if value not in allowed: raise ValueError(f"قيمة '{definition.name}' يجب أن تكون إحدى: {definition.options}")\n        normalized.append((item.definition_id,value))\n    existing={row.spec_definition_id:row for row in db.query(EquipmentModelSpecValue).filter(EquipmentModelSpecValue.equipment_model_id==equipment_model_id).all()}\n    submitted={definition_id for definition_id,_ in normalized}\n    for definition_id,row in existing.items():\n        if definition_id not in submitted: db.delete(row)\n    for definition_id,value in normalized:\n        if definition_id in existing: existing[definition_id].value=value\n        else: db.add(EquipmentModelSpecValue(equipment_model_id=equipment_model_id,spec_definition_id=definition_id,value=value))\n\n'''
s=replace_once(s,needle,specfunc+needle,"spec sync placement")
# Add axle upper-bound validation immediately after duplicate-position validation block using the stable error text from the previous migration.
marker='''    if data.has_tires:\n        keys={(p.axle_number,p.side,p.position_type) for p in data.positions}\n        if len(keys)!=len(data.positions): raise ValueError("توجد مواضع إطارات مكررة")\n'''
if marker not in s:
    marker='''    if data.has_tires:\n        keys={(p.axle_number,p.side,p.position_type) for p in data.positions}\n        if len(keys)!=len(data.positions): raise ValueError("توجد مواضع إطارات مكررة")\n'''
if marker not in s: raise SystemExit("missing duplicate position anchor")
s=s.replace(marker,marker+'''        if data.axle_count is not None:\n            invalid=[p.axle_number for p in data.positions if p.axle_number>data.axle_count]\n            if invalid: raise ValueError(f"رقم المحور {max(invalid)} يتجاوز عدد محاور الطراز المحدد ({data.axle_count})")\n''',1)
# Inject sync before final commit in create_model/update_model blocks.
def inject_sync(text, fn):
    m=re.search(rf'(^def {fn}\(.*?)(?=^def |\Z)', text, re.M|re.S)
    if not m: raise SystemExit(f"missing {fn}")
    block=m.group(1)
    if "_validate_and_sync_specs" in block: return text
    if "db.flush()" not in block: raise SystemExit(f"{fn} has no flush")
    idx=block.rfind("db.commit()")
    if idx<0: raise SystemExit(f"{fn} has no commit")
    block=block[:idx]+'db.flush();_validate_and_sync_specs(db,obj.id,data.specs)\n    '+block[idx:]
    return text[:m.start(1)]+block+text[m.end(1):]
s=inject_sync(s,"create_model")
s=inject_sync(s,"update_model")
write(p,s)

# router.py
p="app/modules/equipment_types/router.py"; s=read(p)
s=replace_once(s,
'EquipmentModelCreate, EquipmentModelOut, EquipmentTypeCreate',
'EquipmentModelCreate, EquipmentModelOut, EquipmentTypeCreate, SpecDefinitionCreate, SpecDefinitionOut, SpecValueInput',
"router schema imports")
s=replace_once(s,
'    models=services.list_models(db);tire_master_data={}',
'    models=services.list_models(db);tire_master_data={};spec_definitions=services.list_spec_definitions(db)',
"router spec definitions")
s=replace_once(s,
'"sizes":[row.size for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==model.id).order_by(TireModelSize.id).all()]}' ,
'"sizes":[row.size for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==model.id).order_by(TireModelSize.id).all()],"specs":[{"definition_id":v.spec_definition_id,"value":v.value} for v in model.spec_values]}' ,
"router model specs")
s=replace_once(s,
'"models":models,"tire_master_data":tire_master_data,"user":current_user}',
'"models":models,"tire_master_data":tire_master_data,"spec_definitions":spec_definitions,"user":current_user}',
"router template context")
# Add admin routes before model create route.
route='''@router.get("/api/equipment-model-spec-definitions",response_model=list[SpecDefinitionOut])\ndef api_list_spec_definitions(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):\n    return services.list_spec_definitions(db)\n\n@router.post("/equipment-types/specs/create")\ndef create_spec_definition_form(name:str=Form(...),data_type:str=Form("text"),unit:str=Form(""),options:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):\n    try: services.create_spec_definition(db,SpecDefinitionCreate(name=name,data_type=data_type,unit=unit or None,options=options or None))\n    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc\n    return _redirect("تمت إضافة الخاصية")\n\n@router.post("/equipment-types/specs/{definition_id}/delete")\ndef delete_spec_definition_form(definition_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):\n    services.delete_spec_definition(db,definition_id)\n    return _redirect("تم حذف الخاصية من كل الطرازات المستخدمة فيها")\n'''
s=replace_once(s,'@router.post("/equipment-types/models/create")',route+'\n@router.post("/equipment-types/models/create")',"spec routes")
# Add specs_json to both model form signatures.
s=s.replace('sizes_json:str=Form("[]"),has_batteries:bool=Form(False)', 'sizes_json:str=Form("[]"),specs_json:str=Form("[]"),has_batteries:bool=Form(False)')
# Parse specs and validate list in both handlers.
s=s.replace('positions_data=json.loads(positions_json);sizes_data=json.loads(sizes_json)\n        if not isinstance(positions_data,list) or not isinstance(sizes_data,list):raise ValueError("بيانات المواضع أو المقاسات غير صالحة")', 'positions_data=json.loads(positions_json);sizes_data=json.loads(sizes_json);specs_data=json.loads(specs_json)\n        if not isinstance(positions_data,list) or not isinstance(sizes_data,list) or not isinstance(specs_data,list):raise ValueError("بيانات المواضع أو المقاسات أو الخصائص غير صالحة")')
s=s.replace('positions=positions_data,sizes=sizes_data,has_batteries=', 'positions=positions_data,sizes=sizes_data,specs=[SpecValueInput.model_validate(x) for x in specs_data],has_batteries=')
write(p,s)

# migration
mig='''"""add equipment_model_spec_definitions and equipment_model_spec_values\n\nrevision: 0031\ndown_revision: 0030_model_axle_count\n"""\nfrom alembic import op\nimport sqlalchemy as sa\n\nrevision = "0031_model_custom_specs"\ndown_revision = "0030_model_axle_count"\nbranch_labels = None\ndepends_on = None\n\ndef upgrade() -> None:\n    bind = op.get_bind()\n    inspector = sa.inspect(bind)\n    tables = set(inspector.get_table_names())\n    if "equipment_model_spec_definitions" not in tables:\n        op.create_table("equipment_model_spec_definitions",\n            sa.Column("id", sa.Integer(), primary_key=True, index=True),\n            sa.Column("name", sa.String(100), nullable=False, unique=True),\n            sa.Column("data_type", sa.String(20), nullable=False, server_default="text"),\n            sa.Column("unit", sa.String(20), nullable=True),\n            sa.Column("options", sa.String(500), nullable=True),\n            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),\n            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),\n            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),\n        )\n    if "equipment_model_spec_values" not in tables:\n        op.create_table("equipment_model_spec_values",\n            sa.Column("id", sa.Integer(), primary_key=True, index=True),\n            sa.Column("equipment_model_id", sa.Integer(), sa.ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=False, index=True),\n            sa.Column("spec_definition_id", sa.Integer(), sa.ForeignKey("equipment_model_spec_definitions.id", ondelete="CASCADE"), nullable=False, index=True),\n            sa.Column("value", sa.String(255), nullable=False),\n            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),\n            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),\n            sa.UniqueConstraint("equipment_model_id", "spec_definition_id", name="uq_model_spec_value"),\n        )\n\ndef downgrade() -> None:\n    bind = op.get_bind()\n    inspector = sa.inspect(bind)\n    tables = set(inspector.get_table_names())\n    if "equipment_model_spec_values" in tables: op.drop_table("equipment_model_spec_values")\n    if "equipment_model_spec_definitions" in tables: op.drop_table("equipment_model_spec_definitions")\n'''
write("migrations/versions/0031_model_custom_specs.py",mig)

# tests
test='''import pytest\nfrom sqlalchemy import create_engine\nfrom sqlalchemy.orm import sessionmaker\nfrom sqlalchemy.pool import StaticPool\nfrom app.database.base import Base\nfrom app.modules.equipment_types.models import EquipmentBrand, EquipmentCategory, EquipmentModel, EquipmentModelSpecDefinition, EquipmentModelSpecValue, EquipmentType\nfrom app.modules.equipment_types.schemas import EquipmentModelCreate, SpecDefinitionCreate, SpecValueInput\nfrom app.modules.equipment_types import services\n\nengine=create_engine("sqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool)\nSession=sessionmaker(bind=engine)\n\ndef db_new():\n    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); return Session()\n\ndef base(db):\n    cat=EquipmentCategory(name="اختبار المواصفات",code="SPECTEST",is_system=True); brand=EquipmentBrand(name="علامة المواصفات",is_active=True); db.add_all([cat,brand]); db.flush(); typ=EquipmentType(name="نوع المواصفات",measurement_unit="km",category_id=cat.id); db.add(typ); db.flush(); return typ,brand\n\ndef model_data(typ,brand,specs=None):\n    return EquipmentModelCreate(name="طراز مواصفات",equipment_type_id=typ.id,brand_id=brand.id,has_tires=False,specs=specs or [])\n\ndef test_number_spec_rejects_non_numeric_and_model_is_not_saved():\n    db=db_new()\n    try:\n        typ,brand=base(db); d=services.create_spec_definition(db,SpecDefinitionCreate(name="الوزن",data_type="number"))\n        with pytest.raises(ValueError,match="يجب أن تكون رقمًا"): services.create_model(db,model_data(typ,brand,[SpecValueInput(definition_id=d.id,value="abc")]))\n        db.rollback(); assert db.query(EquipmentModel).count()==0\n    finally: db.close()\n\ndef test_select_spec_rejects_value_outside_options():\n    db=db_new()\n    try:\n        typ,brand=base(db); d=services.create_spec_definition(db,SpecDefinitionCreate(name="ناقل الحركة",data_type="select",options="يدوي,أوتوماتيك"))\n        with pytest.raises(ValueError,match="إحدى"): services.create_model(db,model_data(typ,brand,[SpecValueInput(definition_id=d.id,value="CVT")]))\n        db.rollback(); assert db.query(EquipmentModel).count()==0\n    finally: db.close()\n\ndef test_empty_spec_is_not_stored():\n    db=db_new()\n    try:\n        typ,brand=base(db); d=services.create_spec_definition(db,SpecDefinitionCreate(name="الحمولة",data_type="number")); model=services.create_model(db,model_data(typ,brand,[SpecValueInput(definition_id=d.id,value=" ")]))\n        assert db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=model.id).count()==0\n    finally: db.close()\n\ndef test_deleting_definition_cascades_values_without_deleting_models():\n    db=db_new()\n    try:\n        typ,brand=base(db); d=services.create_spec_definition(db,SpecDefinitionCreate(name="الوقود")); m1=services.create_model(db,EquipmentModelCreate(name="طراز 1",equipment_type_id=typ.id,brand_id=brand.id,has_tires=False,specs=[SpecValueInput(definition_id=d.id,value="ديزل")])); m2=services.create_model(db,EquipmentModelCreate(name="طراز 2",equipment_type_id=typ.id,brand_id=brand.id,has_tires=False,specs=[SpecValueInput(definition_id=d.id,value="بنزين")]))\n        assert db.query(EquipmentModelSpecValue).count()==2; services.delete_spec_definition(db,d.id)\n        assert db.query(EquipmentModelSpecValue).count()==0; assert db.query(EquipmentModel).filter(EquipmentModel.id.in_([m1.id,m2.id])).count()==2\n    finally: db.close()\n\ndef test_updating_spec_updates_same_value_row():\n    db=db_new()\n    try:\n        typ,brand=base(db); d=services.create_spec_definition(db,SpecDefinitionCreate(name="الوزن",data_type="number")); m=services.create_model(db,model_data(typ,brand,[SpecValueInput(definition_id=d.id,value="100")]))\n        row=db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=m.id,spec_definition_id=d.id).one(); row_id=row.id\n        data=model_data(typ,brand,[SpecValueInput(definition_id=d.id,value="125")]); data.name=m.name; services.update_model(db,m,data)\n        row=db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=m.id,spec_definition_id=d.id).one(); assert row.id==row_id and row.value=="125"\n    finally: db.close()\n\ndef test_missing_definition_id_is_rejected_clearly():\n    db=db_new()\n    try:\n        typ,brand=base(db)\n        with pytest.raises(ValueError,match="لم تعد معرّفة"): services.create_model(db,model_data(typ,brand,[SpecValueInput(definition_id=99999,value="x")]))\n        db.rollback(); assert db.query(EquipmentModel).count()==0\n    finally: db.close()\n'''
write("tests/test_equipment_model_custom_specs.py",test)

# master data workspace template: targeted additions
p="app/modules/equipment_types/templates/master_data_workspace.html"; s=read(p)
s=replace_once(s,'<div class="md-spec"><h3>البطاريات</h3>', '<div class="md-spec"><h3>البطاريات</h3>', "battery anchor")
s=replace_once(s,'<div class="md-spec"><h3>البطاريات</h3><label class="md-check">', '<div class="md-spec"><h3>البطاريات</h3><label class="md-check">', "battery section")
# Insert custom specs editor before action buttons.
s=replace_once(s,'<div class="md-actions"><button type="submit"', '''<div class="md-spec" id="customSpecs"><h3>خصائص إضافية</h3><div id="customSpecsFields" class="md-fields"></div><div class="disabled-note">كل الخصائص اختيارية ولا تؤثر على قواعد العمل.</div></div>\n<div class="md-actions"><button type="submit"''',"custom specs editor")
# Add fifth tab and panel.
s=replace_once(s,'<button type="button" data-tab="categories">الفئات</button></div>', '<button type="button" data-tab="categories">الفئات</button><button type="button" data-tab="specs">الخصائص</button></div>',"spec tab")
panel='''<div id="panel-specs" class="md-panel"><div class="table-wrap"><table><thead><tr><th>الاسم</th><th>النوع</th><th>الوحدة</th><th>القيم المسموحة</th><th>إجراء</th></tr></thead><tbody>{% for spec in spec_definitions %}<tr><td>{{ spec.name }}</td><td>{{ 'نص' if spec.data_type=='text' else ('رقم' if spec.data_type=='number' else 'اختيار') }}</td><td>{{ spec.unit or '—' }}</td><td>{{ spec.options or '—' }}</td><td><form method="post" action="/equipment-types/specs/{{ spec.id }}/delete" onsubmit="return confirm('سيؤدي حذف هذه الخاصية إلى حذف قيمتها من كل الطرازات التي استخدمتها. متابعة؟');"><button type="submit" class="mini-btn danger">حذف</button></form></td></tr>{% else %}<tr><td colspan="5">لا توجد خصائص معرفة.</td></tr>{% endfor %}</tbody></table></div><form method="post" action="/equipment-types/specs/create" class="md-fields" style="margin-top:14px"><label>اسم الخاصية<input name="name" required></label><label>النوع<select name="data_type" id="specDataType"><option value="text">نص</option><option value="number">رقم</option><option value="select">اختيار</option></select></label><label>الوحدة<input name="unit" placeholder="اختياري"></label><label id="specOptionsField" style="display:none">القيم المسموحة<input name="options" placeholder="يدوي,أوتوماتيك,CVT"></label><div class="md-actions"><button class="primary" type="submit">إضافة خاصية</button></div></form></div>'''
s=replace_once(s,'<div id="panel-categories" class="md-panel">',panel+'\n<div id="panel-categories" class="md-panel">',"spec panel")
# Add specs data attribute to edit button.
s=replace_once(s,'data-sizes=\'{{ td.sizes|tojson|e }}\'>تعديل', 'data-sizes=\'{{ td.sizes|tojson|e }}\' data-specs=\'{{ td.specs|tojson|e }}\'>تعديل',"model specs data")
# Add global definitions and dynamic rendering after existing const declaration.
s=replace_once(s,'let positions=[], sizes=[];', 'let positions=[], sizes=[];\nconst specDefinitions={{ spec_definitions|tojson }};\nlet currentSpecs={};\nfunction renderCustomSpecs(values){const fields=document.getElementById("customSpecsFields");fields.innerHTML="";currentSpecs={};const byId={};(values||[]).forEach(v=>byId[String(v.definition_id)]=v.value);specDefinitions.forEach(d=>{const label=document.createElement("label");label.dataset.definitionId=d.id;const title=document.createElement("span");title.textContent=d.name+(d.unit?` (${d.unit})`:"");label.appendChild(title);let input;if(d.data_type==="select"){input=document.createElement("select");(d.options||"").split(",").map(x=>x.trim()).filter(Boolean).forEach(o=>{const opt=document.createElement("option");opt.value=o;opt.textContent=o;input.appendChild(opt)});}else{input=document.createElement("input");input.type=d.data_type==="number"?"number":"text";if(d.data_type==="number")input.step="any";}input.dataset.specInput="1";input.dataset.definitionId=d.id;input.value=byId[String(d.id)]||"";label.appendChild(input);fields.appendChild(label);});}\nrenderCustomSpecs([]);')
# Update newModel to clear specs if function is present.
s=s.replace("document.getElementById('newModel').onclick=()=>{", "document.getElementById('newModel').onclick=()=>{")
# Inject specs into edit handler generically after data sizes parsing.
s=s.replace("sizes=JSON.parse(this.dataset.sizes||'[]');", "sizes=JSON.parse(this.dataset.sizes||'[]');renderCustomSpecs(JSON.parse(this.dataset.specs||'[]'));")
# If the template's handler uses a different assignment style, ensure render call exists near data-sizes.
if 'renderCustomSpecs(JSON.parse(this.dataset.specs||\'[]\'))' not in s:
    raise SystemExit("edit handler specs anchor missing")
# Ensure newModel clears fields.
s=s.replace("sizes=[];refresh();", "sizes=[];renderCustomSpecs([]);refresh();")
# Prepare submit: inject specs JSON before return.
if 'name="specs_json"' not in s:
    s=s.replace('function prepareModelSubmit(event){', 'function prepareModelSubmit(event){')
    # Find first occurrence of positionsJson.value assignment in function and insert before it.
    marker='positionsJson.value=JSON.stringify(positions);'
    s=replace_once(s,marker,'const specs=[...document.querySelectorAll("[data-spec-input=\\"1\\"]")].map(input=>({definition_id:Number(input.dataset.definitionId),value:input.value.trim()})).filter(x=>x.value);let specsField=f.querySelector("[name=\\"specs_json\\"]");if(!specsField){specsField=document.createElement("input");specsField.type="hidden";specsField.name="specs_json";f.appendChild(specsField)}specsField.value=JSON.stringify(specs);'+marker,"spec submit")
# Show/hide select options field.
s += '''\n<script>document.getElementById('specDataType')?.addEventListener('change',function(){document.getElementById('specOptionsField').style.display=this.value==='select'?'flex':'none'});</script>\n'''
write(p,s)

# equipment detail chips
p="app/modules/equipment/templates/equipment_detail.html"; s=read(p)
anchor='{% if item.equipment_model.battery_voltage_v %}<div class="record-box"><span>الجهد</span><b>{{ item.equipment_model.battery_voltage_v }} V</b></div>{% endif %}'
chips=anchor+'{% for spec in item.equipment_model.spec_values %}<div class="record-box"><span>{{ spec.definition.name }}</span><b>{{ spec.value }}{% if spec.definition.unit %} {{ spec.definition.unit }}{% endif %}</b></div>{% endfor %}'
s=replace_once(s,anchor,chips,"equipment detail custom spec chips")
write(p,s)

# remove temporary implementation files from final tree
(Path(__file__).resolve().parent / 'apply_custom_specs.py').unlink()
(Path(__file__).resolve().parents[1] / 'workflows' / 'apply-custom-specs.yml').unlink()
print("custom specs implementation applied")
