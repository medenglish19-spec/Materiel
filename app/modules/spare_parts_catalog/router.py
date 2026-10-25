from __future__ import annotations

from math import ceil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.faults_repairs.models import SparePart
from app.modules.users.models import User
from .models import SparePartCatalogDetails, SparePartCatalogImport, SparePartCatalogReference, SparePartCategory
from . import services

router = APIRouter()
templates = get_module_templates("app/modules/spare_parts_catalog/templates")


def _catalog_context(request, user, db, *, q="", page=1, category_id=None, manufacturer=None, source=None, active=None, error=None, notice=None, active_dialog=None):
    query = db.query(SparePart, SparePartCatalogDetails).outerjoin(
        SparePartCatalogDetails, SparePartCatalogDetails.spare_part_id == SparePart.id
    )
    if q:
        like = f"%{q[:100]}%"
        reference_ids = db.query(SparePartCatalogReference.spare_part_id).filter(SparePartCatalogReference.reference.ilike(like))
        query = query.filter(or_(SparePart.name.ilike(like), SparePart.part_number.ilike(like), SparePartCatalogDetails.name_ar.ilike(like), SparePartCatalogDetails.name_fr.ilike(like), SparePartCatalogDetails.original_name.ilike(like), SparePartCatalogDetails.manufacturer.ilike(like), SparePart.id.in_(reference_ids)))
    if category_id:
        query = query.filter(SparePartCatalogDetails.category_id == category_id)
    if manufacturer:
        query = query.filter(SparePartCatalogDetails.manufacturer == manufacturer)
    if source:
        query = query.filter(SparePartCatalogDetails.source == source)
    if active is not None:
        if active:
            query = query.filter(or_(SparePartCatalogDetails.is_active.is_(True), SparePartCatalogDetails.id.is_(None)))
        else:
            query = query.filter(SparePartCatalogDetails.is_active.is_(False))
    total = query.count()
    page_size = 25
    page = max(1, min(page, max(1, ceil(total / page_size))))
    items = query.order_by(SparePart.name, SparePart.id).offset((page - 1) * page_size).limit(page_size).all()
    part_ids = [part.id for part, _ in items]
    references = {}
    if part_ids:
        for ref in db.query(SparePartCatalogReference).filter(SparePartCatalogReference.spare_part_id.in_(part_ids)).order_by(SparePartCatalogReference.id).all():
            references.setdefault(ref.spare_part_id, []).append(ref)
    categories = db.query(SparePartCategory).filter(SparePartCategory.is_active.is_(True)).order_by(SparePartCategory.sort_order, SparePartCategory.name_ar).all()
    category_paths = {}
    for category in categories:
        names = [category.name_ar]
        parent = category.parent
        while parent and len(names) < 8:
            names.append(parent.name_ar)
            parent = parent.parent
        category_paths[category.id] = " / ".join(reversed(names))
    manufacturers = [row[0] for row in db.query(SparePartCatalogDetails.manufacturer).filter(SparePartCatalogDetails.manufacturer.is_not(None)).distinct().order_by(SparePartCatalogDetails.manufacturer).all()]
    sources = [row[0] for row in db.query(SparePartCatalogDetails.source).filter(SparePartCatalogDetails.source.is_not(None)).distinct().order_by(SparePartCatalogDetails.source).all()]
    return {"request": request, "user": user, "items": items, "references": references, "categories": categories, "category_paths": category_paths, "manufacturers": manufacturers, "sources": sources, "q": q, "page": page, "page_size": page_size, "total": total, "category_id": category_id, "manufacturer_filter": manufacturer, "source_filter": source, "active_filter": active, "error": error, "notice": notice, "active_dialog": active_dialog}


@router.get("/spare-parts/catalog", response_class=HTMLResponse)
def catalog_page(request: Request, q: str = "", page: int = 1, category_id: int | None = None, manufacturer: str | None = None, source: str | None = None, active: bool | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, q=q, page=page, category_id=category_id, manufacturer=manufacturer, source=source, active=active))


@router.post("/spare-parts/catalog/categories")
def create_category(request: Request, name_ar: str = Form(...), name_fr: str = Form(""), parent_id: int | None = Form(None), db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    name_ar = name_ar.strip()
    if not name_ar or len(name_ar) > 120 or len(name_fr) > 120:
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="اسم التصنيف بالعربية مطلوب وبحد أقصى 120 حرفًا.", active_dialog="category"), status_code=422)
    parent = db.get(SparePartCategory, parent_id) if parent_id else None
    if parent_id and not parent:
        raise HTTPException(404, "التصنيف الأب غير موجود.")
    query = db.query(SparePartCategory).filter(SparePartCategory.name_ar == name_ar)
    query = query.filter(SparePartCategory.parent_id == (parent.id if parent else None))
    if query.first():
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="يوجد تصنيف بهذا الاسم ضمن المستوى نفسه.", active_dialog="category"), status_code=409)
    db.add(SparePartCategory(name_ar=name_ar, name_fr=name_fr.strip() or None, parent_id=parent.id if parent else None))
    db.commit()
    return RedirectResponse("/spare-parts/catalog", status_code=303)


@router.post("/spare-parts/catalog/categories/{category_id}/update")
def update_category(category_id: int, request: Request, name_ar: str = Form(...), name_fr: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    category = db.get(SparePartCategory, category_id)
    if not category:
        raise HTTPException(404, "التصنيف غير موجود.")
    name_ar = name_ar.strip()
    name_fr = name_fr.strip()
    if not name_ar or len(name_ar) > 120 or len(name_fr) > 120:
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="اسم التصنيف بالعربية مطلوب وبحد أقصى 120 حرفًا.", active_dialog="category"), status_code=422)
    duplicate = db.query(SparePartCategory.id).filter(
        SparePartCategory.name_ar == name_ar,
        SparePartCategory.parent_id == category.parent_id,
        SparePartCategory.id != category.id,
    ).first()
    if duplicate:
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="يوجد تصنيف بهذا الاسم ضمن المستوى نفسه.", active_dialog="category"), status_code=409)
    category.name_ar = name_ar
    category.name_fr = name_fr or None
    db.commit()
    return RedirectResponse("/spare-parts/catalog", status_code=303)


@router.post("/spare-parts/catalog/categories/{category_id}/delete")
def delete_category(category_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    category = db.get(SparePartCategory, category_id)
    if not category:
        raise HTTPException(404, "التصنيف غير موجود.")
    if db.query(SparePartCategory.id).filter(SparePartCategory.parent_id == category.id).first():
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="لا يمكن حذف التصنيف لأنه يحتوي تصنيفات فرعية.", active_dialog="category"), status_code=409)
    if db.query(SparePartCatalogDetails.id).filter(SparePartCatalogDetails.category_id == category.id).first():
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="لا يمكن حذف التصنيف لأنه مرتبط بقطع غيار.", active_dialog="category"), status_code=409)
    db.delete(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error="تعذر حذف التصنيف بسبب ارتباطه ببيانات أخرى.", active_dialog="category"), status_code=409)
    return RedirectResponse("/spare-parts/catalog", status_code=303)


def _make_part(db: Session, *, name, name_ar, name_fr, reference, manufacturer, category, notes, source, image_path=None):
    name = (name or name_fr or name_ar or "").strip()
    if not name or len(name) > 160:
        raise ValueError("اسم القطعة مطلوب وبحد أقصى 160 حرفًا.")
    reference = (reference or "").strip()
    if len(reference) > 120:
        raise ValueError("المرجع لا يتجاوز 120 حرفًا.")
    manufacturer = (manufacturer or "").strip()[:160]
    if reference and db.query(SparePartCatalogReference.id).filter(
        SparePartCatalogReference.reference == reference,
        SparePartCatalogReference.manufacturer == (manufacturer or None),
    ).first():
        raise ValueError("المرجع مسجل لهذه الشركة؛ راجع القطعة الموجودة بدل تكرارها.")
    part = SparePart(part_number="CAT-" + uuid.uuid4().hex[:16].upper(), name=name, receiving_document=None, notes=(notes or "").strip() or None)
    db.add(part)
    db.flush()
    cat = services._category_for_path(db, category or "")
    db.add(SparePartCatalogDetails(
        spare_part_id=part.id,
        category_id=cat.id if cat else None,
        name_ar=(name_ar or "").strip()[:160] or None,
        name_fr=(name_fr or "").strip()[:160] or None,
        original_name=name[:255],
        manufacturer=manufacturer or None,
        source=(source or "").strip()[:255] or None,
        image_path=image_path,
    ))
    if reference:
        db.add(SparePartCatalogReference(spare_part_id=part.id, manufacturer=manufacturer or None, reference=reference, source=(source or "").strip()[:255] or None))
    return part


@router.post("/spare-parts/catalog/parts")
async def create_part(request: Request, name: str = Form(""), name_ar: str = Form(""), name_fr: str = Form(""), reference: str = Form(""), manufacturer: str = Form(""), category: str = Form(""), notes: str = Form(""), source: str = Form(""), image: UploadFile | None = File(None), db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    image_path = None
    try:
        if image and image.filename:
            image_path = services.store_image(await image.read(5 * 1024 * 1024 + 1), image.filename)
        _make_part(db, name=name, name_ar=name_ar, name_fr=name_fr, reference=reference, manufacturer=manufacturer, category=category, notes=notes, source=source, image_path=image_path)
        db.commit()
    except ValueError as exc:
        db.rollback()
        services.remove_image(image_path)
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error=str(exc), active_dialog="part"), status_code=422)
    except Exception:
        db.rollback()
        services.remove_image(image_path)
        raise
    return RedirectResponse("/spare-parts/catalog", status_code=303)


@router.post("/spare-parts/catalog/parts/{part_id}/update")
async def update_part(part_id: int, request: Request, name: str = Form(...), name_ar: str = Form(""), name_fr: str = Form(""), reference: str = Form(""), manufacturer: str = Form(""), category: str = Form(""), notes: str = Form(""), source: str = Form(""), active: str = Form("on"), remove_image: str = Form(""), image: UploadFile | None = File(None), db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    part = db.get(SparePart, part_id)
    if not part:
        raise HTTPException(404, "قطعة الغيار غير موجودة.")
    details = db.query(SparePartCatalogDetails).filter_by(spare_part_id=part.id).first()
    if not details:
        details = SparePartCatalogDetails(spare_part_id=part.id)
        db.add(details)
    uploaded_image_path = None
    try:
        old_image_path = details.image_path
        if not name.strip() or len(name.strip()) > 160:
            raise ValueError("اسم القطعة مطلوب وبحد أقصى 160 حرفًا.")
        part.name = name.strip()[:160]
        part.notes = notes.strip() or None
        details.name_ar = name_ar.strip()[:160] or None
        details.name_fr = name_fr.strip()[:160] or None
        details.original_name = name.strip()[:255] or None
        details.manufacturer = manufacturer.strip()[:160] or None
        details.source = source.strip()[:255] or None
        details.is_active = active == "on"
        details.category = services._category_for_path(db, category)
        if remove_image == "on":
            details.image_path = None
        if image and image.filename:
            uploaded_image_path = services.store_image(await image.read(5 * 1024 * 1024 + 1), image.filename)
            details.image_path = uploaded_image_path
        if reference.strip():
            existing_ref = db.query(SparePartCatalogReference).filter(
                SparePartCatalogReference.reference == reference.strip()[:120],
                SparePartCatalogReference.manufacturer == (details.manufacturer or None),
                SparePartCatalogReference.spare_part_id != part.id,
            ).first()
            if existing_ref:
                raise ValueError("المرجع مسجل لقطعة أخرى لدى الشركة نفسها.")
            ref = db.query(SparePartCatalogReference).filter_by(spare_part_id=part.id).first()
            if ref:
                ref.reference = reference.strip()[:120]
                ref.manufacturer = details.manufacturer
                ref.source = details.source
            else:
                db.add(SparePartCatalogReference(spare_part_id=part.id, reference=reference.strip()[:120], manufacturer=details.manufacturer, source=details.source))
        db.commit()
        if details.image_path != old_image_path:
            services.remove_image(old_image_path)
    except ValueError as exc:
        db.rollback()
        services.remove_image(uploaded_image_path)
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error=str(exc), active_dialog="part"), status_code=422)
    except Exception:
        db.rollback()
        services.remove_image(uploaded_image_path)
        raise
    return RedirectResponse("/spare-parts/catalog", status_code=303)


@router.post("/spare-parts/catalog/parts/{part_id}/delete")
def delete_part(part_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    part = db.get(SparePart, part_id)
    if not part:
        raise HTTPException(404, "قطعة الغيار غير موجودة.")
    try:
        image_path = services.delete_catalog_part(db, part)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return templates.TemplateResponse(request=request, name="catalog.html", context=_catalog_context(request, user, db, error=str(exc)), status_code=409)
    except Exception:
        db.rollback()
        raise
    services.remove_image(image_path)
    return RedirectResponse("/spare-parts/catalog", status_code=303)


@router.get("/spare-parts/catalog/import", response_class=HTMLResponse)
def import_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="import.html", context={"request": request, "user": user})


@router.post("/spare-parts/catalog/import", response_class=HTMLResponse)
async def import_preview(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    from .services import MAX_UPLOAD_BYTES, create_import_preview, preview_data

    try:
        from app.modules.document_import.upload import read_upload_bytes, UploadTooLargeError
        data = await read_upload_bytes(file, MAX_UPLOAD_BYTES)
        batch = create_import_preview(db, file.filename or "catalog", data, user.id)
        db.commit()
        db.refresh(batch)
    except ValueError as exc:
        db.rollback()
        return templates.TemplateResponse(request=request, name="import.html", context={"request": request, "user": user, "error": str(exc)}, status_code=413 if isinstance(exc, UploadTooLargeError) else 400)
    return templates.TemplateResponse(request=request, name="import.html", context={"request": request, "user": user, "batch": batch, **preview_data(batch, include_images=True)})


@router.post("/spare-parts/catalog/import/{batch_id}/apply", response_class=HTMLResponse)
async def import_apply(batch_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER))):
    form = await request.form()
    try:
        result = services.apply_import(db, batch_id, form, user.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "تعارض أثناء اعتماد الاستيراد. لم تُحفظ الدفعة؛ أعد المعاينة ثم حاول مجددًا.") from exc
    batch = db.get(SparePartCatalogImport, batch_id)
    return templates.TemplateResponse(request=request, name="import.html", context={"request": request, "user": user, "batch": batch, **services.preview_data(batch), "result": result})
