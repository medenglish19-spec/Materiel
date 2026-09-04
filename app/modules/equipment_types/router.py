from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment_types import services
from app.modules.equipment_types.schemas import (
    EquipmentBrandCreate,
    EquipmentBrandOut,
    EquipmentCategoryCreate,
    EquipmentCategoryOut,
    EquipmentModelCreate,
    EquipmentModelOut,
    EquipmentTypeCreate,
    EquipmentTypeOut,
)
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/equipment_types/templates")


@router.get("/equipment-types", response_class=HTMLResponse)
def types_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    types = services.list_types(db)
    categories = services.list_categories(db)
    brands = services.list_brands(db)
    return templates.TemplateResponse(
        "types_list.html",
        {
            "request": request,
            "types": types,
            "categories": categories,
            "brands": brands,
            "user": current_user,
        },
    )


@router.post("/equipment-types/categories/create")
def create_category_form(
    name: str = Form(...),
    code: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    try:
        services.create_category(db, EquipmentCategoryCreate(name=name, code=code or None))
    except ValueError:
        pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/categories/{category_id}/delete")
def delete_category_form(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    obj = services.get_category(db, category_id)
    if obj:
        try:
            services.delete_category(db, obj)
        except ValueError:
            pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/create")
def create_type_form(
    request: Request,
    name: str = Form(...),
    measurement_unit: str = Form(...),
    category_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    try:
        services.create_type(
            db,
            EquipmentTypeCreate(
                name=name,
                measurement_unit=measurement_unit,
                category_id=int(category_id) if category_id else None,
            ),
        )
    except (ValueError, TypeError):
        pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/{type_id}/category")
def set_type_category_form(
    type_id: int,
    category_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    obj = services.get_type(db, type_id)
    if obj:
        try:
            services.set_type_category(db, obj, int(category_id) if category_id else None)
        except (ValueError, TypeError):
            pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/{type_id}/delete")
def delete_type_form(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    obj = services.get_type(db, type_id)
    if obj:
        services.delete_type(db, obj)
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/brands/create")
def create_brand_form(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    try:
        services.create_brand(db, EquipmentBrandCreate(name=name))
    except ValueError:
        pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/models/create")
def create_model_form(
    request: Request,
    name: str = Form(...),
    equipment_type_id: int = Form(...),
    brand_id: str = Form(""),
    theoretical_quantity: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    try:
        services.create_model(
            db,
            EquipmentModelCreate(
                name=name,
                equipment_type_id=equipment_type_id,
                brand_id=int(brand_id) if brand_id else None,
                theoretical_quantity=max(0, theoretical_quantity),
            ),
        )
    except (ValueError, TypeError):
        pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/models/{model_id}/brand")
def set_model_brand_form(
    model_id: int,
    brand_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    obj = services.get_model(db, model_id)
    if obj:
        try:
            services.set_model_brand(db, obj, int(brand_id) if brand_id else None)
        except (ValueError, TypeError):
            pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/models/{model_id}/theoretical-quantity")
def set_model_theoretical_quantity_form(
    model_id: int,
    theoretical_quantity: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    obj = services.get_model(db, model_id)
    if obj:
        try:
            services.set_model_theoretical_quantity(db, obj, theoretical_quantity)
        except ValueError:
            pass
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.post("/equipment-types/models/{model_id}/delete")
def delete_model_form(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    obj = services.get_model(db, model_id)
    if obj:
        services.delete_model(db, obj)
    return RedirectResponse(url="/equipment-types", status_code=status.HTTP_302_FOUND)


@router.get("/api/equipment-types", response_model=list[EquipmentTypeOut])
def api_list_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return services.list_types(db)


@router.get("/api/equipment-types/{type_id}/models", response_model=list[EquipmentModelOut])
def api_list_models(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return services.list_models(db, type_id=type_id)


@router.get("/api/equipment-categories", response_model=list[EquipmentCategoryOut])
def api_list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return services.list_categories(db)


@router.get("/api/equipment-brands", response_model=list[EquipmentBrandOut])
def api_list_brands(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return services.list_brands(db)
