from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
import json
from pathlib import Path
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from urllib.parse import quote
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment_types import demo, services
from app.modules.equipment_types.models import EquipmentCategory, EquipmentBrand, EquipmentType, EquipmentModel, EquipmentModelSpecDefinition, EquipmentModelSpecValue, equipment_type_spec_definitions
from app.modules.equipment_types.presenters import model_editor_payloads
from app.modules.equipment.models import Equipment
from app.modules.maintenance.models import MaintenancePlan
from app.modules.tires.models import TirePosition, TireModelSize, TireMovement
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandOut, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryOut, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentModelOut, EquipmentTypeCreate, EquipmentTypeOut, EquipmentTypeUpdate, SpecDefinitionCreate, SpecDefinitionOut, SpecValueInput
from app.modules.users.models import User
router=APIRouter();templates=get_module_templates("app/modules/equipment_types/templates")

@router.get("/api/equipment-types/categories/{category_id}/delete-impact")
def category_delete_impact(category_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_category(db,category_id)
    if obj is None:raise HTTPException(status_code=404,detail="الفئة غير موجودة")
    type_count=db.query(EquipmentType.id).filter(EquipmentType.category_id==obj.id).count()
    spec_count=db.query(EquipmentModelSpecDefinition.id).filter(EquipmentModelSpecDefinition.category_id==obj.id).count()
    return {"label":obj.name,"effects":[{"label":"أنواع العتاد المرتبطة (تمنع الحذف)","count":type_count,"kind":"blocked"},{"label":"تعريفات الخصائص التي ستبقى بلا فئة","count":spec_count,"kind":"unlink"}],"blocked":"لا يمكن حذف فئة النظام." if obj.is_system else ("انقل أنواع العتاد إلى فئة أخرى أولًا." if type_count else None)}

@router.get("/api/equipment-types/brands/{brand_id}/delete-impact")
def brand_delete_impact(brand_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_brand(db,brand_id)
    if obj is None:raise HTTPException(status_code=404,detail="العلامة التجارية غير موجودة")
    model_count=db.query(EquipmentModel.id).filter(EquipmentModel.brand_id==obj.id).count()
    return {"label":obj.name,"effects":[{"label":"طرازات مرتبطة (تمنع الحذف)","count":model_count,"kind":"blocked"}],"blocked":"انقل الطرازات المرتبطة إلى علامة أخرى أولًا." if model_count else None}

@router.get("/api/equipment-types/{type_id}/delete-impact")
def type_delete_impact(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj is None:raise HTTPException(status_code=404,detail="نوع العتاد غير موجود")
    model_ids=[row[0] for row in db.query(EquipmentModel.id).filter(EquipmentModel.equipment_type_id==obj.id).all()]
    equipment_count=db.query(Equipment.id).filter(Equipment.equipment_type_id==obj.id).count()
    plan_count=db.query(MaintenancePlan.id).filter(MaintenancePlan.equipment_model_id.in_(model_ids)).count() if model_ids else 0
    positions=db.query(TirePosition.id).filter(TirePosition.equipment_model_id.in_(model_ids)).all() if model_ids else []
    position_ids=[row[0] for row in positions]
    size_count=db.query(TireModelSize.id).filter(TireModelSize.equipment_model_id.in_(model_ids)).count() if model_ids else 0
    spec_value_count=db.query(EquipmentModelSpecValue.id).filter(EquipmentModelSpecValue.equipment_model_id.in_(model_ids)).count() if model_ids else 0
    type_spec_count=len(db.execute(equipment_type_spec_definitions.select().where(equipment_type_spec_definitions.c.equipment_type_id==obj.id)).fetchall())
    effects=[
        {"label":"العتاد الفعلي الذي يمنع الحذف","count":equipment_count,"kind":"blocked"},
        {"label":"الطرازات التابعة التي ستحذف","count":len(model_ids)},
        {"label":"خطط الصيانة التابعة للطرازات التي ستحذف","count":plan_count},
        {"label":"قيم الخصائص الفنية التابعة التي ستحذف","count":spec_value_count},
        {"label":"مقاسات الإطارات التابعة التي ستحذف","count":size_count},
        {"label":"روابط الخصائص الفنية بنوع العتاد التي ستحذف","count":type_spec_count},
        {"label":"مواضع الإطارات التابعة التي ستحذف","count":len(position_ids)},
        {"label":"حركات الإطارات التي ستبقى بلا موضع","count":db.query(TireMovement.id).filter(TireMovement.position_id.in_(position_ids)).count() if position_ids else 0,"kind":"unlink"},
    ]
    blocked="نوع العتاد مجمد؛ أعد اعتماده أولًا." if obj.is_frozen else ("لا يمكن حذف نوع مرتبط بعتاد فعلي." if equipment_count else None)
    return {"label":obj.name,"effects":effects,"blocked":blocked}

@router.get("/api/equipment-types/models/{model_id}/delete-impact")
def model_delete_impact(model_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj is None:raise HTTPException(status_code=404,detail="الطراز غير موجود")
    equipment_count=db.query(Equipment.id).filter(Equipment.equipment_model_id==obj.id).count()
    plan_count=db.query(MaintenancePlan.id).filter(MaintenancePlan.equipment_model_id==obj.id).count()
    position_ids=[row[0] for row in db.query(TirePosition.id).filter(TirePosition.equipment_model_id==obj.id).all()]
    size_count=db.query(TireModelSize.id).filter(TireModelSize.equipment_model_id==obj.id).count()
    value_count=db.query(EquipmentModelSpecValue.id).filter(EquipmentModelSpecValue.equipment_model_id==obj.id).count()
    return {"label":obj.name,"effects":[
        {"label":"العتاد الفعلي الذي يمنع الحذف","count":equipment_count,"kind":"blocked"},
        {"label":"خطط الصيانة التي ستحذف","count":plan_count},
        {"label":"قيم الخصائص الفنية التي ستحذف","count":value_count},
        {"label":"مقاسات الإطارات المعتمدة التي ستحذف","count":size_count},
        {"label":"مواضع الإطارات التي ستحذف","count":len(position_ids)},
        {"label":"حركات الإطارات التي ستبقى بلا موضع","count":db.query(TireMovement.id).filter(TireMovement.position_id.in_(position_ids)).count() if position_ids else 0,"kind":"unlink"},
    ],"blocked":"الطراز مجمد؛ أعد اعتماده أولًا." if obj.is_frozen else ("لا يمكن حذف طراز مرتبط بعتاد فعلي." if equipment_count else None)}

@router.get("/api/equipment-types/specs/{definition_id}/delete-impact")
def spec_delete_impact(definition_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=db.get(EquipmentModelSpecDefinition,definition_id)
    if obj is None:raise HTTPException(status_code=404,detail="الخاصية غير موجودة")
    values=db.query(EquipmentModelSpecValue).filter(EquipmentModelSpecValue.spec_definition_id==obj.id).count()
    type_links=db.execute(equipment_type_spec_definitions.select().where(equipment_type_spec_definitions.c.spec_definition_id==obj.id)).fetchall()
    return {"label":obj.name,"effects":[{"label":"قيم الخاصية في الطرازات التي ستحذف","count":values},{"label":"روابط الخاصية بأنواع العتاد التي ستحذف","count":len(type_links)}]}
_TREE_JS=Path(__file__).resolve().parents[3]/"static"/"js"/"master-data-tree.js"
def _tree_js_version()->str:
    try:return "mtime-"+str(int(_TREE_JS.stat().st_mtime))
    except OSError:return "master-data-workspace-7"
def _redirect(notice:str|None=None,notice_type:str="success"):
    if notice is None:return RedirectResponse(url="/equipment-types",status_code=303)
    return RedirectResponse(url="/equipment-types?notice_type="+notice_type+"&notice="+quote(notice),status_code=303)
@router.get("/equipment-types",response_class=HTMLResponse)
def types_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    models=services.list_models(db);types=services.list_types(db);categories=services.list_categories(db);brands=services.list_brands(db)
    equipment_type_counts=dict(db.query(Equipment.equipment_type_id,func.count(Equipment.id)).group_by(Equipment.equipment_type_id).all())
    equipment_model_counts=dict(db.query(Equipment.equipment_model_id,func.count(Equipment.id)).filter(Equipment.equipment_model_id.isnot(None)).group_by(Equipment.equipment_model_id).all())
    spec_type_ids=services.list_spec_definition_type_ids(db)
    spec_definitions=[{"id":d.id,"name":d.name,"code":d.code,"data_type":d.data_type,"unit":d.unit,"options":d.options,"group_name":d.group_name,"group_sort_order":d.group_sort_order,"equipment_type_id":d.equipment_type_id,"category_id":d.category_id,"equipment_type_ids":spec_type_ids.get(d.id,[])} for d in services.list_spec_definitions(db)]
    editor_payloads=model_editor_payloads(db,models)
    model_by_id={model.id:model for model in models}
    for payload in editor_payloads:
        model=model_by_id[payload["id"]]
        payload["is_frozen"]=bool(model.is_frozen)
        payload["actual_count"]=equipment_model_counts.get(model.id,0)
    model_ids=[model.id for model in models]
    linked_equipment={model_id:[] for model_id in model_ids}
    equipment_rows=(db.query(Equipment).filter(Equipment.equipment_model_id.in_(model_ids)).order_by(Equipment.registration_number,Equipment.id).all() if model_ids else [])
    for item in equipment_rows:
        linked_equipment.setdefault(item.equipment_model_id,[]).append({"id":item.id,"registration_number":item.registration_number,"asset_code":item.asset_code,"operational_status":item.operational_status,"technical_condition":item.technical_condition,"odometer":float(item.current_odometer) if item.current_odometer is not None else None,"hours":float(item.current_hours) if item.current_hours is not None else None})
    tire_master_data={p["id"]:p for p in editor_payloads}
    response = templates.TemplateResponse(request=request, name="master_data_workspace.html", context={"request":request,"types":types,"categories":categories,"brands":brands,"models":models,"equipment_type_counts":equipment_type_counts,"equipment_model_counts":equipment_model_counts,"linked_equipment":linked_equipment,"tire_master_data":tire_master_data,"spec_definitions":spec_definitions,"tree_js_version":_tree_js_version(),"user":current_user})
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
@router.get("/equipment-types/structure",response_class=HTMLResponse)
def equipment_types_structure_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    models=services.list_models(db);counts=dict(db.query(Equipment.equipment_model_id,func.count(Equipment.id)).filter(Equipment.equipment_model_id.isnot(None)).group_by(Equipment.equipment_model_id).all())
    return templates.TemplateResponse(request=request, name="equipment_types_structure.html", context={"request":request,"models":models,"actual_counts":counts,"user":current_user})
@router.post("/equipment-types/demo")
def create_demo_form(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):services.create_demo_classification(db);return _redirect()
@router.post("/equipment-types/demo/delete")
def delete_demo_form(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:demo.delete_demo_classification(db)
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    return _redirect()
@router.post("/equipment-types/categories/create")
def create_category_form(name:str=Form(...),code:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:services.create_category(db,EquipmentCategoryCreate(name=name,code=code or None))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تمت إضافة الفئة")
@router.post("/equipment-types/categories/{category_id}/update")
def update_category_form(category_id:int,name:str=Form(...),code:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_category(db,category_id)
    if obj is None:raise HTTPException(status_code=404,detail="الفئة غير موجودة")
    try:services.update_category(db,obj,EquipmentCategoryUpdate(name=name,code=code or None))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تم حفظ تعديل الفئة")
@router.post("/equipment-types/categories/{category_id}/delete")
def delete_category_form(category_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_category(db,category_id)
    if obj:
        try:services.delete_category(db,obj)
        except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    return _redirect("تم حذف الفئة")
@router.post("/equipment-types/create")
def create_type_form(name:str=Form(...),measurement_unit:str=Form(...),category_id:int=Form(...),theoretical_quantity:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:services.create_type(db,EquipmentTypeCreate(name=name,measurement_unit=measurement_unit,category_id=category_id,theoretical_quantity=None if not theoretical_quantity.strip() else int(theoretical_quantity)))
    except (ValueError,TypeError) as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تمت إضافة نوع العتاد")
@router.post("/equipment-types/{type_id}/update")
def update_type_form(type_id:int,name:str=Form(...),measurement_unit:str=Form(...),category_id:int=Form(...),theoretical_quantity:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj is None:raise HTTPException(status_code=404,detail="نوع العتاد غير موجود")
    try:services.update_type(db,obj,EquipmentTypeUpdate(name=name,measurement_unit=measurement_unit,category_id=category_id,theoretical_quantity=None if not theoretical_quantity.strip() else int(theoretical_quantity)))
    except (ValueError,TypeError) as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تم حفظ تعديل نوع العتاد")
@router.post("/equipment-types/{type_id}/category")
def set_type_category_form(type_id:int,category_id:int=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj:
        try:services.set_type_category(db,obj,category_id)
        except (ValueError,TypeError) as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تم حفظ الفئة")
@router.post("/equipment-types/{type_id}/theoretical-quantity")
def set_type_theoretical_quantity_form(type_id:int,theoretical_quantity:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj:
        try:services.set_type_theoretical_quantity(db,obj,None if not theoretical_quantity.strip() else int(theoretical_quantity))
        except (ValueError,TypeError) as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تم حفظ التعداد النظري")
@router.post("/equipment-types/{type_id}/freeze")
def freeze_type_form(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj is None:raise HTTPException(status_code=404,detail="نوع العتاد غير موجود")
    services.set_type_frozen(db,obj,True);return _redirect("تم إيقاف اعتماد نوع العتاد")
@router.post("/equipment-types/{type_id}/unfreeze")
def unfreeze_type_form(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj is None:raise HTTPException(status_code=404,detail="نوع العتاد غير موجود")
    services.set_type_frozen(db,obj,False);return _redirect("تمت إعادة اعتماد نوع العتاد")
@router.post("/equipment-types/{type_id}/delete")
def delete_type_form(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj:
        try:services.delete_type(db,obj)
        except (ValueError,TypeError) as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    return _redirect("تم حذف نوع العتاد")
@router.post("/equipment-types/brands/create")
def create_brand_form(name:str=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:services.create_brand(db,EquipmentBrandCreate(name=name))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تمت إضافة العلامة التجارية")
@router.post("/equipment-types/brands/{brand_id}/update")
def update_brand_form(brand_id:int,name:str=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_brand(db,brand_id)
    if obj is None:raise HTTPException(status_code=404,detail="العلامة التجارية غير موجودة")
    try:services.update_brand(db,obj,EquipmentBrandUpdate(name=name))
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تم حفظ تعديل العلامة التجارية")
@router.post("/equipment-types/brands/{brand_id}/delete")
def delete_brand_form(brand_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_brand(db,brand_id)
    if obj is None: raise HTTPException(status_code=404,detail="العلامة التجارية غير موجودة")
    try: services.delete_brand(db,obj)
    except ValueError as exc: return _redirect(str(exc),"warning")
    return _redirect("تم حذف العلامة التجارية")

@router.post("/equipment-types/brands/{brand_id}/toggle")
def toggle_brand_form(brand_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_brand(db,brand_id)
    if obj is None:raise HTTPException(status_code=404,detail="العلامة التجارية غير موجودة")
    services.set_brand_active(db,obj,not obj.is_active);return _redirect("تم تحديث حالة العلامة التجارية")
@router.get("/api/equipment-model-spec-definitions",response_model=list[SpecDefinitionOut])
def api_list_spec_definitions(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))): return services.list_spec_definitions(db)
@router.post("/equipment-types/specs/create")
def create_spec_definition_form(name:str=Form(...),code:str=Form(""),data_type:str=Form("text"),unit:str=Form(""),options:str=Form(""),group_name:str=Form(""),group_sort_order:int=Form(0),equipment_type_id:str=Form(""),category_id:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try: services.create_spec_definition(db,SpecDefinitionCreate(name=name,code=code or None,data_type=data_type,unit=unit or None,options=options or None,group_name=group_name or None,group_sort_order=group_sort_order,equipment_type_id=int(equipment_type_id) if equipment_type_id.strip() else None,category_id=int(category_id) if category_id.strip() else None))
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تمت إضافة الخاصية")
@router.post("/equipment-types/specs/{definition_id}/delete")
def delete_spec_definition_form(definition_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    services.delete_spec_definition(db,definition_id);return _redirect("تم حذف الخاصية من كل الطرازات المستخدمة فيها")
@router.post("/equipment-types/models/create")
async def create_model_form(request:Request,name:str=Form(...),equipment_type_id:int=Form(...),has_tires:bool=Form(False),tire_positions_required:int=Form(0),axle_count:str=Form(""),tire_size:str=Form(""),positions_json:str=Form("[]"),sizes_json:str=Form("[]"),specs_json:str=Form("[]"),has_batteries:bool=Form(False),battery_count_required:int=Form(0),battery_capacity_ah:str=Form(""),battery_voltage_v:str=Form(""),mobility_type:str=Form("mobile"),requires_driver:bool=Form(False),image_url:str=Form(""),image:UploadFile|None=File(None),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    uploaded_image_url = None
    try:
        if image and image.filename:
            uploaded_image_url = services.store_model_image(await image.read(5 * 1024 * 1024 + 1), image.filename)
        positions_data=json.loads(positions_json);sizes_data=json.loads(sizes_json);specs_data=json.loads(specs_json)
        if not isinstance(positions_data,list) or not isinstance(sizes_data,list) or not isinstance(specs_data,list):raise ValueError("بيانات المواضع أو المقاسات أو الخصائص غير صالحة")
        form=await request.form(); brand_raw=str(form.get("brand_id") or "").strip(); brand_value=int(brand_raw) if brand_raw else None
        services.create_model(db,EquipmentModelCreate(name=name,equipment_type_id=equipment_type_id,brand_id=brand_value,has_tires=has_tires,tire_positions_required=tire_positions_required,axle_count=None if not axle_count.strip() else int(axle_count),tire_size=tire_size.strip() or None,positions=positions_data,sizes=sizes_data,specs=[SpecValueInput.model_validate(x) for x in specs_data],has_batteries=has_batteries,battery_count_required=battery_count_required,battery_capacity_ah=None if not battery_capacity_ah.strip() else float(battery_capacity_ah),battery_voltage_v=None if not battery_voltage_v.strip() else float(battery_voltage_v),mobility_type=mobility_type,requires_driver=requires_driver,image_url=uploaded_image_url or image_url.strip() or None))
    except (ValueError,TypeError) as exc:
        db.rollback();services.remove_model_image(uploaded_image_url);return _redirect(str(exc),"warning")
    except Exception:
        db.rollback();services.remove_model_image(uploaded_image_url);raise
    return _redirect("تمت إضافة الطراز والمواصفات")
@router.post("/equipment-types/models/{model_id}/update")
async def update_model_form(request:Request,model_id:int,name:str=Form(...),equipment_type_id:int=Form(...),has_tires:bool=Form(False),tire_positions_required:int=Form(0),axle_count:str=Form(""),tire_size:str=Form(""),positions_json:str=Form("[]"),sizes_json:str=Form("[]"),specs_json:str=Form("[]"),has_batteries:bool=Form(False),battery_count_required:int=Form(0),battery_capacity_ah:str=Form(""),battery_voltage_v:str=Form(""),mobility_type:str=Form("mobile"),requires_driver:bool=Form(False),image_url:str=Form(""),image:UploadFile|None=File(None),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj is None:raise HTTPException(status_code=404,detail="طراز العتاد غير موجود")
    old_image_url = obj.image_url
    uploaded_image_url = None
    try:
        if image and image.filename:
            uploaded_image_url = services.store_model_image(await image.read(5 * 1024 * 1024 + 1), image.filename)
        positions_data=json.loads(positions_json);sizes_data=json.loads(sizes_json);specs_data=json.loads(specs_json)
        if not isinstance(positions_data,list) or not isinstance(sizes_data,list) or not isinstance(specs_data,list):raise ValueError("بيانات المواضع أو المقاسات أو الخصائص غير صالحة")
        form=await request.form(); brand_raw=str(form.get("brand_id") or "").strip(); brand_value=int(brand_raw) if brand_raw else None
        services.update_model(db,obj,EquipmentModelCreate(name=name,equipment_type_id=equipment_type_id,brand_id=brand_value,has_tires=has_tires,tire_positions_required=tire_positions_required,axle_count=None if not axle_count.strip() else int(axle_count),tire_size=tire_size.strip() or None,positions=positions_data,sizes=sizes_data,specs=[SpecValueInput.model_validate(x) for x in specs_data],has_batteries=has_batteries,battery_count_required=battery_count_required,battery_capacity_ah=None if not battery_capacity_ah.strip() else float(battery_capacity_ah),battery_voltage_v=None if not battery_voltage_v.strip() else float(battery_voltage_v),mobility_type=mobility_type,requires_driver=requires_driver,image_url=uploaded_image_url or image_url.strip() or None))
    except (ValueError,TypeError) as exc:
        db.rollback();services.remove_model_image(uploaded_image_url);return _redirect(str(exc),"warning")
    except Exception:
        db.rollback();services.remove_model_image(uploaded_image_url);raise
    if uploaded_image_url and old_image_url != uploaded_image_url:
        services.remove_model_image(old_image_url)
    return _redirect("تم حفظ تعديلات الطراز والمواصفات")
@router.post("/equipment-types/models/{model_id}/move")
def move_model_form(model_id:int,equipment_type_id:int=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj is None: raise HTTPException(status_code=404,detail="طراز العتاد غير موجود")
    try: services.move_model_to_type(db,obj,equipment_type_id)
    except (ValueError,TypeError) as exc: return _redirect(str(exc),"warning")
    return _redirect("تم نقل الطراز داخل الشجرة")
@router.post("/equipment-types/models/{model_id}/brand")
def set_model_brand_form(model_id:int,brand_id:int=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj:
        try:services.set_model_brand(db,obj,brand_id)
        except (ValueError,TypeError) as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تم حفظ العلامة التجارية")
@router.post("/equipment-types/models/{model_id}/freeze")
def freeze_model_form(model_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj is None:raise HTTPException(status_code=404,detail="طراز العتاد غير موجود")
    services.set_model_frozen(db,obj,True);return _redirect("تم إيقاف اعتماد طراز العتاد")
@router.post("/equipment-types/models/{model_id}/unfreeze")
def unfreeze_model_form(model_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj is None:raise HTTPException(status_code=404,detail="طراز العتاد غير موجود")
    services.set_model_frozen(db,obj,False);return _redirect("تمت إعادة اعتماد طراز العتاد")
@router.post("/equipment-types/models/{model_id}/delete")
def delete_model_form(model_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj:
        image_url = obj.image_url
        try:
            services.delete_model(db,obj)
            services.remove_model_image(image_url)
        except (ValueError,TypeError) as exc:return _redirect(str(exc),"warning")
    return _redirect("تم حذف الطراز بنجاح")
@router.get("/api/equipment-types",response_model=list[EquipmentTypeOut])
def api_list_types(db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_types(db)
@router.get("/api/equipment-types/{type_id}/models",response_model=list[EquipmentModelOut])
def api_list_models(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_models(db,type_id=type_id)
@router.get("/api/equipment-categories",response_model=list[EquipmentCategoryOut])
def api_list_categories(db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_categories(db)
@router.get("/api/equipment-brands",response_model=list[EquipmentBrandOut])
def api_list_brands(db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_brands(db)

