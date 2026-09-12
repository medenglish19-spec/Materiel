from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment import demo, services as equipment_services
from app.modules.equipment.models import Equipment
from app.modules.equipment_types import services
from app.modules.equipment_types.master_data_import import import_master_data
from app.modules.equipment_types.master_data_editor import get_editor_data, save_editor_data
from app.modules.equipment_types.schemas import EquipmentBrandCreate, EquipmentBrandOut, EquipmentCategoryCreate, EquipmentCategoryOut, EquipmentModelCreate, EquipmentModelOut, EquipmentTypeCreate, EquipmentTypeOut
from app.modules.users.models import User
router=APIRouter();templates=get_module_templates("app/modules/equipment_types/templates")
@router.get("/equipment-types",response_class=HTMLResponse)
def types_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):return templates.TemplateResponse("types_list.html",{"request":request,"types":services.list_types(db),"categories":services.list_categories(db),"brands":services.list_brands(db),"models":services.list_models(db),"user":current_user})
@router.get("/equipment-types/structure",response_class=HTMLResponse)
def equipment_types_structure_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    models=services.list_models(db)
    counts=dict(db.query(Equipment.equipment_model_id,func.count(Equipment.id)).filter(Equipment.equipment_model_id.isnot(None)).group_by(Equipment.equipment_model_id).all())
    return templates.TemplateResponse("equipment_types_structure.html",{"request":request,"models":models,"actual_counts":counts,"user":current_user})
@router.get("/equipment-types/master-data",response_class=HTMLResponse)
def master_data_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    models=services.list_models(db)
    return templates.TemplateResponse("master_data_editor.html",{"request":request,"models":models,"selected_model_id":models[0].id if models else None,"user":current_user})
@router.get("/equipment-types/master-data/{model_id}/data")
def master_data_editor_data(model_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:return JSONResponse(get_editor_data(db,model_id))
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc
@router.post("/equipment-types/master-data/{model_id}/data")
async def master_data_editor_save(model_id:int,request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:
        payload=await request.json()
        if not isinstance(payload,dict):raise ValueError("بيانات الحفظ غير صحيحة.")
        return JSONResponse(save_editor_data(db,model_id,payload))
    except ValueError as exc:
        db.rollback();raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception:
        db.rollback();raise
@router.get("/equipment-types/master-data/import",response_class=HTMLResponse)
def master_data_import_page(request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    return templates.TemplateResponse("master_data_import.html",{"request":request,"user":current_user})
@router.post("/equipment-types/master-data/import",response_class=HTMLResponse)
async def master_data_import_form(request:Request,file:UploadFile=File(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return templates.TemplateResponse("master_data_import.html",{"request":request,"user":current_user,"error":"يرجى اختيار ملف Excel بصيغة .xlsx"},status_code=400)
    content=await file.read()
    if not content:
        return templates.TemplateResponse("master_data_import.html",{"request":request,"user":current_user,"error":"الملف فارغ"},status_code=400)
    try:
        result=import_master_data(db,content)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return templates.TemplateResponse("master_data_import.html",{"request":request,"user":current_user,"error":str(exc)},status_code=400)
    except Exception:
        db.rollback()
        raise
    return templates.TemplateResponse("master_data_import.html",{"request":request,"user":current_user,"result":result})
@router.post("/equipment-types/demo")
def create_demo_form(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):services.create_demo_classification(db);return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/demo/delete")
def delete_demo_form(db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:demo.delete_demo_classification(db)
    except ValueError as exc:raise HTTPException(status_code=409,detail=str(exc)) from exc
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/categories/create")
def create_category_form(name:str=Form(...),code:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:services.create_category(db,EquipmentCategoryCreate(name=name,code=code or None))
    except ValueError:pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/categories/{category_id}/delete")
def delete_category_form(category_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_category(db,category_id)
    if obj:
        try:services.delete_category(db,obj)
        except ValueError:pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/create")
def create_type_form(name:str=Form(...),measurement_unit:str=Form(...),category_id:int=Form(...),theoretical_quantity:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:services.create_type(db,EquipmentTypeCreate(name=name,measurement_unit=measurement_unit,category_id=category_id,theoretical_quantity=None if not theoretical_quantity.strip() else int(theoretical_quantity)))
    except (ValueError,TypeError):pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/{type_id}/category")
def set_type_category_form(type_id:int,category_id:int=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj:
        try:services.set_type_category(db,obj,category_id)
        except (ValueError,TypeError):pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/{type_id}/theoretical-quantity")
def set_type_theoretical_quantity_form(type_id:int,theoretical_quantity:str=Form(""),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj:
        try:services.set_type_theoretical_quantity(db,obj,None if not theoretical_quantity.strip() else int(theoretical_quantity))
        except (ValueError,TypeError):pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/{type_id}/delete")
def delete_type_form(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_type(db,type_id)
    if obj:services.delete_type(db,obj)
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/brands/create")
def create_brand_form(name:str=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:services.create_brand(db,EquipmentBrandCreate(name=name))
    except ValueError:pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/models/create")
def create_model_form(name:str=Form(...),equipment_type_id:int=Form(...),brand_id:int=Form(...),has_tires:bool=Form(False),tire_positions_required:int=Form(0),tire_size:str=Form(""),has_batteries:bool=Form(False),battery_count_required:int=Form(0),battery_capacity_ah:str=Form(""),battery_voltage_v:str=Form(""),mobility_type:str=Form("mobile"),requires_driver:bool=Form(True),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    try:
        services.create_model(db,EquipmentModelCreate(name=name,equipment_type_id=equipment_type_id,brand_id=brand_id,has_tires=has_tires,tire_positions_required=tire_positions_required,tire_size=tire_size.strip() or None,has_batteries=has_batteries,battery_count_required=battery_count_required,battery_capacity_ah=None if not battery_capacity_ah.strip() else float(battery_capacity_ah),battery_voltage_v=None if not battery_voltage_v.strip() else float(battery_voltage_v),mobility_type=mobility_type,requires_driver=requires_driver))
    except (ValueError,TypeError):pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/models/{model_id}/brand")
def set_model_brand_form(model_id:int,brand_id:int=Form(...),db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj:
        try:services.set_model_brand(db,obj,brand_id)
        except (ValueError,TypeError):pass
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.post("/equipment-types/models/{model_id}/delete")
def delete_model_form(model_id:int,db:Session=Depends(get_db),current_user:User=Depends(require_role(Role.ADMIN))):
    obj=services.get_model(db,model_id)
    if obj:services.delete_model(db,obj)
    return RedirectResponse(url="/equipment-types",status_code=302)
@router.get("/api/equipment-types",response_model=list[EquipmentTypeOut])
def api_list_types(db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_types(db)
@router.get("/api/equipment-types/{type_id}/models",response_model=list[EquipmentModelOut])
def api_list_models(type_id:int,db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_models(db,type_id=type_id)
@router.get("/api/equipment-categories",response_model=list[EquipmentCategoryOut])
def api_list_categories(db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_categories(db)
@router.get("/api/equipment-brands",response_model=list[EquipmentBrandOut])
def api_list_brands(db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):return services.list_brands(db)