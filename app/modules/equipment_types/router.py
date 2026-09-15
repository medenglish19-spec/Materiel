from fastapi import APIRouter, Depends, Form, HTTPException, Request
import json
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from urllib.parse import quote
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment_types import demo, services
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandOut, EquipmentBrandUpdate, EquipmentCategoryCreate, EquipmentCategoryOut, EquipmentCategoryUpdate, EquipmentModelCreate, EquipmentModelOut, EquipmentTypeCreate, EquipmentTypeOut, EquipmentTypeUpdate, SpecDefinitionCreate, SpecDefinitionOut, SpecValueInput
from app.modules.users.models import User
from app.modules.tires.models import TireModelSize, TirePosition
router=APIRouter();templates=get_module_templates("app/modules/equipment_types/templates")
def _redirect(notice:str|None=None,notice_type:str="success"):
    if notice is None:return RedirectResponse(url="/equipment-types",status_code=303)
    return RedirectResponse(url="/equipment-types?notice_type="+notice_type+"&notice="+quote(notice),status_code=303)
@router.get("/equipment-types",response_class=HTMLResponse)
def types_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    models=services.list_models(db);tire_master_data={}
    spec_definitions=[{"id":d.id,"name":d.name,"data_type":d.data_type,"unit":d.unit,"options":d.options} for d in services.list_spec_definitions(db)]
    for model in models:
        tire_master_data[model.id]={"positions":[{"id":p.id,"axle_number":p.axle_number,"side":p.side,"position_type":p.position_type,"description":p.description} for p in db.query(TirePosition).filter(TirePosition.equipment_model_id==model.id).order_by(TirePosition.axle_number,TirePosition.sort_order,TirePosition.id).all()],"sizes":[row.size for row in db.query(TireModelSize).filter(TireModelSize.equipment_model_id==model.id).order_by(TireModelSize.id).all()],"specs":[{"definition_id":v.spec_definition_id,"value":v.value} for v in model.spec_values]}
    return templates.TemplateResponse("master_data_workspace.html",{"request":request,"types":services.list_types(db),"categories":services.list_categories(db),"brands":services.list_brands(db),"models":models,"tire_master_data":tire_master_data,"spec_definitions":spec_definitions,"user":current_user})
@router.get("/equipment-types/structure",response_class=HTMLResponse)
def equipment_types_structure_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    models=services.list_models(db);counts=dict(db.query(Equipment.equipment_model_id,func.count(Equipment.id)).filter(Equipment.equipment_model_id.isnot(None)).group_by(Equipment.equipment_model_id).all())
    return templates.TemplateResponse("equipment_types_structure.html",{"request":request,"models":models,"actual_counts":counts,"user":current_user})
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
@router.post("/equipment-types/brands/{brand_id}/toggle")
def toggle_brand_form(brand_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_brand(db,brand_id)
    if obj is None:raise HTTPException(status_code=404,detail="العلامة التجارية غير موجودة")
    services.set_brand_active(db,obj,not obj.is_active);return _redirect("تم تحديث حالة العلامة التجارية")
@router.get("/api/equipment-model-spec-definitions",response_model=list[SpecDefinitionOut])
def api_list_spec_definitions(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))): return services.list_spec_definitions(db)
@router.post("/equipment-types/specs/create")
def create_spec_definition_form(name:str=Form(...),data_type:str=Form("text"),unit:str=Form(""),options:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try: services.create_spec_definition(db,SpecDefinitionCreate(name=name,data_type=data_type,unit=unit or None,options=options or None))
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    return _redirect("تمت إضافة الخاصية")
@router.post("/equipment-types/specs/{definition_id}/delete")
def delete_spec_definition_form(definition_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    services.delete_spec_definition(db,definition_id);return _redirect("تم حذف الخاصية من كل الطرازات المستخدمة فيها")
@router.post("/equipment-types/models/create")
def create_model_form(name:str=Form(...),equipment_type_id:int=Form(...),brand_id:int=Form(...),has_tires:bool=Form(False),tire_positions_required:int=Form(0),axle_count:str=Form(""),tire_size:str=Form(""),positions_json:str=Form("[]"),sizes_json:str=Form("[]"),specs_json:str=Form("[]"),has_batteries:bool=Form(False),battery_count_required:int=Form(0),battery_capacity_ah:str=Form(""),battery_voltage_v:str=Form(""),mobility_type:str=Form("mobile"),requires_driver:bool=Form(True),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:
        positions_data=json.loads(positions_json);sizes_data=json.loads(sizes_json);specs_data=json.loads(specs_json)
        if not isinstance(positions_data,list) or not isinstance(sizes_data,list) or not isinstance(specs_data,list):raise ValueError("بيانات المواضع أو المقاسات أو الخصائص غير صالحة")
        services.create_model(db,EquipmentModelCreate(name=name,equipment_type_id=equipment_type_id,brand_id=brand_id,has_tires=has_tires,tire_positions_required=tire_positions_required,axle_count=None if not axle_count.strip() else int(axle_count),tire_size=tire_size.strip() or None,positions=positions_data,sizes=sizes_data,specs=[SpecValueInput.model_validate(x) for x in specs_data],has_batteries=has_batteries,battery_count_required=battery_count_required,battery_capacity_ah=None if not battery_capacity_ah.strip() else float(battery_capacity_ah),battery_voltage_v=None if not battery_voltage_v.strip() else float(battery_voltage_v),mobility_type=mobility_type,requires_driver=requires_driver))
    except (ValueError,TypeError) as exc:
        db.rollback();return _redirect(str(exc),"warning")
    return _redirect("تمت إضافة الطراز والمواصفات")
@router.post("/equipment-types/models/{model_id}/update")
def update_model_form(model_id:int,name:str=Form(...),equipment_type_id:int=Form(...),brand_id:int=Form(...),has_tires:bool=Form(False),tire_positions_required:int=Form(0),axle_count:str=Form(""),tire_size:str=Form(""),positions_json:str=Form("[]"),sizes_json:str=Form("[]"),specs_json:str=Form("[]"),has_batteries:bool=Form(False),battery_count_required:int=Form(0),battery_capacity_ah:str=Form(""),battery_voltage_v:str=Form(""),mobility_type:str=Form("mobile"),requires_driver:bool=Form(True),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj is None:raise HTTPException(status_code=404,detail="طراز العتاد غير موجود")
    try:
        positions_data=json.loads(positions_json);sizes_data=json.loads(sizes_json);specs_data=json.loads(specs_json)
        if not isinstance(positions_data,list) or not isinstance(sizes_data,list) or not isinstance(specs_data,list):raise ValueError("بيانات المواضع أو المقاسات أو الخصائص غير صالحة")
        services.update_model(db,obj,EquipmentModelCreate(name=name,equipment_type_id=equipment_type_id,brand_id=brand_id,has_tires=has_tires,tire_positions_required=tire_positions_required,axle_count=None if not axle_count.strip() else int(axle_count),tire_size=tire_size.strip() or None,positions=positions_data,sizes=sizes_data,specs=[SpecValueInput.model_validate(x) for x in specs_data],has_batteries=has_batteries,battery_count_required=battery_count_required,battery_capacity_ah=None if not battery_capacity_ah.strip() else float(battery_capacity_ah),battery_voltage_v=None if not battery_voltage_v.strip() else float(battery_voltage_v),mobility_type=mobility_type,requires_driver=requires_driver))
    except (ValueError,TypeError) as exc:
        db.rollback();return _redirect(str(exc),"warning")
    return _redirect("تم حفظ تعديلات الطراز والمواصفات")
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
        try:services.delete_model(db,obj)
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