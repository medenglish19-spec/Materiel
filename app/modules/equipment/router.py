from typing import Optional
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment import services
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentOut, EquipmentUpdate
from app.modules.equipment_types import services as type_services
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.users.models import User
from app.modules.meter_readings import services as meter_services
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.audit import MeterReadingChange, utc_now

router = APIRouter()
templates = get_module_templates("app/modules/equipment/templates")


@router.get("/equipment", response_class=HTMLResponse)
def equipment_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = services.list_equipment(db)
    types = type_services.list_types(db)
    return templates.TemplateResponse("equipment_list.html", {"request": request, "items": items, "types": types, "user": current_user})


@router.get("/equipment/analysis", response_class=HTMLResponse)
def equipment_analysis_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(Equipment).options(joinedload(Equipment.equipment_type).joinedload(EquipmentType.category), joinedload(Equipment.equipment_model)).order_by(Equipment.id).all()
    categories = {}
    ready = ready_restricted = broken = 0
    for item in items:
        category = item.equipment_type.category if item.equipment_type else None
        category_name = category.name if category else "غير مصنف"
        type_name = item.equipment_type.name if item.equipment_type else "بدون نوع"
        model_name = item.equipment_model.name if item.equipment_model else "بدون طراز"
        theoretical = int(item.equipment_model.theoretical_quantity or 0) if item.equipment_model else 0
        cg = categories.setdefault(category_name, {"types": {}, "actual": 0, "ready": 0, "broken": 0})
        tg = cg["types"].setdefault(type_name, {"models": {}, "actual": 0, "ready": 0, "broken": 0})
        mg = tg["models"].setdefault(model_name, {"theoretical": theoretical, "actual": 0, "ready": 0, "ready_restricted": 0, "broken": 0})
        mg["theoretical"] = max(mg["theoretical"], theoretical)
        mg["actual"] += 1; tg["actual"] += 1; cg["actual"] += 1
        if item.technical_condition == "ready":
            ready += 1; mg["ready"] += 1; tg["ready"] += 1; cg["ready"] += 1
        elif item.technical_condition == "ready_restricted":
            ready_restricted += 1; mg["ready_restricted"] += 1; tg["ready_restricted"] += 1; cg["ready_restricted"] += 1
        else:
            broken += 1; mg["broken"] += 1; tg["broken"] += 1; cg["broken"] += 1
    for cg in categories.values():
        cg["theoretical"] = sum(m["theoretical"] for t in cg["types"].values() for m in t["models"].values())
        cg["need"] = max(0, cg["theoretical"] - cg["actual"])
        for tg in cg["types"].values():
            tg["theoretical"] = sum(m["theoretical"] for m in tg["models"].values())
            tg["need"] = max(0, tg["theoretical"] - tg["actual"])
            for mg in tg["models"].values():
                mg["need"] = max(0, mg["theoretical"] - mg["actual"])
    totals_theoretical = sum(c["theoretical"] for c in categories.values())
    totals_actual = len(items)
    return templates.TemplateResponse("equipment_analysis.html", {"request": request, "user": current_user, "categories": categories, "totals": {"theoretical": totals_theoretical, "actual": totals_actual, "need": max(0, totals_theoretical - totals_actual), "ready": ready, "broken": broken, "readiness": round(ready / totals_actual * 100, 1) if totals_actual else 0}})


@router.get("/equipment/numerical-status", response_class=HTMLResponse)
def equipment_numerical_status_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(Equipment).options(
        joinedload(Equipment.equipment_type).joinedload(EquipmentType.category),
        joinedload(Equipment.equipment_model).joinedload(EquipmentModel.brand),
    ).order_by(Equipment.id).all()
    models = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.equipment_type).joinedload(EquipmentType.category),
        joinedload(EquipmentModel.brand),
    ).order_by(EquipmentModel.id).all()

    keys = ("total", "theoretical", "ready", "broken", "available", "in_mission", "in_maintenance", "in_external_workshop", "unavailable", "need", "surplus", "outside_ted")
    zero = lambda: {k: 0 for k in keys}
    groups = {}

    for model in models:
        equipment_type = model.equipment_type
        category = equipment_type.category if equipment_type else None
        category_name = category.name if category else "غير مصنف"
        type_name = equipment_type.name if equipment_type else "بدون نوع"
        model_name = model.name or "بدون طراز"
        brand_name = model.brand.name if model.brand else "بدون ماركة"
        cg = groups.setdefault(category_name, {"types": {}, "sort": category.sort_order if category else 9999})
        tg = cg["types"].setdefault(type_name, {"models": {}})
        key = (brand_name, model_name)
        tg["models"].setdefault(
            key,
            dict(zero(), theoretical=int(model.theoretical_quantity or 0), brand=brand_name, model=model_name, equipment=[]),
        )

    for item in items:
        category = item.equipment_type.category if item.equipment_type else None
        category_name = category.name if category else "غير مصنف"
        type_name = item.equipment_type.name if item.equipment_type else "بدون نوع"
        model_name = item.equipment_model.name if item.equipment_model else "بدون طراز"
        brand_name = item.equipment_model.brand.name if item.equipment_model and item.equipment_model.brand else "بدون ماركة"
        cg = groups.setdefault(category_name, {"types": {}, "sort": category.sort_order if category else 9999})
        tg = cg["types"].setdefault(type_name, {"models": {}})
        theoretical = int(item.equipment_model.theoretical_quantity or 0) if item.equipment_model else 0
        key = (brand_name, model_name)
        mg = tg["models"].setdefault(
            key,
            dict(zero(), theoretical=theoretical, brand=brand_name, model=model_name, equipment=[]),
        )
        mg["total"] += 1
        mg["theoretical"] = max(mg["theoretical"], theoretical)
        mg["equipment"].append({
            "id": item.id,
            "asset_code": item.asset_code,
            "registration_number": item.registration_number,
            "technical_condition": item.technical_condition,
            "operational_status": item.operational_status,
        })
        condition = item.technical_condition if item.technical_condition in ("ready", "ready_restricted", "broken") else "ready"
        mg[condition] += 1
        if item.operational_status in keys:
            mg[item.operational_status] += 1

    def finalize(stats):
        stats["outside_ted"] = stats["total"] if stats["theoretical"] <= 0 else 0
        stats["need"] = max(0, stats["theoretical"] - (stats["total"] - stats["outside_ted"])) if stats["theoretical"] > 0 else 0
        stats["surplus"] = max(0, (stats["total"] - stats["outside_ted"]) - stats["theoretical"]) if stats["theoretical"] > 0 else 0
        return stats

    def add_percentages(stats, parent_total=None):
        base = stats["total"] or 0
        parent = parent_total or 0
        ted_actual = max(0, base - stats.get("outside_ted", 0))
        stats["ted_actual"] = ted_actual
        stats["parent_pct"] = (base / parent * 100) if parent else (100.0 if base else 0.0)
        stats["coverage_pct"] = (ted_actual / stats["theoretical"] * 100) if stats["theoretical"] else 0.0
        stats["need_pct"] = (stats["need"] / stats["theoretical"] * 100) if stats["theoretical"] else 0.0
        stats["surplus_pct"] = (stats["surplus"] / stats["theoretical"] * 100) if stats["theoretical"] else 0.0
        stats["ready_pct"] = (stats["ready"] / base * 100) if base else 0.0
        stats["broken_pct"] = (stats["broken"] / base * 100) if base else 0.0
        stats["available_pct"] = (stats["available"] / base * 100) if base else 0.0
        stats["mission_pct"] = (stats["in_mission"] / base * 100) if base else 0.0
        stats["maintenance_pct"] = (stats["in_maintenance"] / base * 100) if base else 0.0
        stats["external_pct"] = (stats["in_external_workshop"] / base * 100) if base else 0.0
        stats["unavailable_pct"] = (stats["unavailable"] / base * 100) if base else 0.0
        return stats

    def sum_stats(stats_list):
        out = zero()
        for st in stats_list:
            for k in keys:
                out[k] += st.get(k, 0)
        return out

    model_details = {}
    hierarchy = []
    for category_name, cg in sorted(groups.items(), key=lambda x: (x[1]["sort"], x[0])):
        type_rows = []
        for type_name, tg in sorted(cg["types"].items()):
            model_rows = []
            for model_key_tuple, st in sorted(tg["models"].items()):
                finalize(st)
                model_key = "{}::{}::{}::{}".format(category_name, type_name, model_key_tuple[0], model_key_tuple[1])
                display_name = ((st.get("brand") + " — ") if st.get("brand") and st.get("brand") != "بدون ماركة" else "") + st.get("model", model_key_tuple[1])
                model_details[model_key] = {
                    "name": display_name,
                    "theoretical": st["theoretical"],
                    "total": st["total"],
                    "need": st["need"],
                    "surplus": st["surplus"],
                    "outside_ted": st["outside_ted"],
                    "equipment": st["equipment"],
                }
                model_rows.append({"name": display_name, "key": model_key, "stats": st})
            ts = sum_stats([m["stats"] for m in model_rows])
            type_rows.append({"name": type_name, "stats": ts, "models": model_rows})
        cs = sum_stats([t["stats"] for t in type_rows])
        hierarchy.append({"name": category_name, "stats": cs, "types": type_rows})

    totals = sum_stats([c["stats"] for c in hierarchy])
    totals["equipment"] = totals["total"]
    totals["ted_actual"] = max(0, totals["total"] - totals["outside_ted"])

    for category in hierarchy:
        add_percentages(category["stats"], totals["total"])
        for type_row in category["types"]:
            add_percentages(type_row["stats"], category["stats"]["total"])
            for model_row in type_row["models"]:
                add_percentages(model_row["stats"], type_row["stats"]["total"])
    add_percentages(totals, totals["total"])

    category_analysis = sorted([
        {"name": c["name"], "total": c["stats"]["total"], "theoretical": c["stats"]["theoretical"], "need": c["stats"]["need"], "surplus": c["stats"]["surplus"], "outside_ted": c["stats"]["outside_ted"], "share": c["stats"]["parent_pct"], "coverage": c["stats"]["coverage_pct"], "ready": c["stats"]["ready_pct"], "broken": c["stats"]["broken_pct"]}
        for c in hierarchy
    ], key=lambda x: x["total"], reverse=True)

    type_analysis = []
    model_analysis = []
    for c in hierarchy:
        for t in c["types"]:
            type_analysis.append({"category": c["name"], "name": t["name"], "total": t["stats"]["total"], "theoretical": t["stats"]["theoretical"], "need": t["stats"]["need"], "surplus": t["stats"]["surplus"], "outside_ted": t["stats"]["outside_ted"], "share": t["stats"]["parent_pct"], "coverage": t["stats"]["coverage_pct"], "ready": t["stats"]["ready_pct"], "broken": t["stats"]["broken_pct"]})
            for m in t["models"]:
                model_analysis.append({"category": c["name"], "type": t["name"], "name": ((m["stats"].get("brand") + " — ") if m["stats"].get("brand") and m["stats"].get("brand") != "بدون ماركة" else "") + m["stats"].get("model", m["name"]), "total": m["stats"]["total"], "theoretical": m["stats"]["theoretical"], "need": m["stats"]["need"], "surplus": m["stats"]["surplus"], "outside_ted": m["stats"]["outside_ted"], "share": m["stats"]["parent_pct"], "coverage": m["stats"]["coverage_pct"], "ready": m["stats"]["ready_pct"], "broken": m["stats"]["broken_pct"]})

    type_analysis.sort(key=lambda x: x["total"], reverse=True)
    model_analysis.sort(key=lambda x: (x["need"], -x["coverage"]), reverse=True)
    status_analysis = [
        {"name": "جاهز", "count": totals["ready"], "pct": totals["ready_pct"]},
        {"name": "عاطل", "count": totals["broken"], "pct": totals["broken_pct"]},
        {"name": "متاح", "count": totals["available"], "pct": totals["available_pct"]},
        {"name": "في مهمة", "count": totals["in_mission"], "pct": totals["mission_pct"]},
        {"name": "في الصيانة", "count": totals["in_maintenance"], "pct": totals["maintenance_pct"]},
        {"name": "ورشة خارجية", "count": totals["in_external_workshop"], "pct": totals["external_pct"]},
        {"name": "غير متاح", "count": totals["unavailable"], "pct": totals["unavailable_pct"]},
    ]
    analysis = {
        "category_count": len(category_analysis),
        "type_count": len(type_analysis),
        "model_count": len(model_analysis),
        "coverage": totals["coverage_pct"],
        "need_pct": totals["need_pct"],
        "surplus_pct": totals["surplus_pct"],
        "ready_pct": totals["ready_pct"],
        "broken_pct": totals["broken_pct"],
        "operational_availability_pct": totals["available_pct"],
        "maintenance_load_pct": totals["maintenance_pct"],
        "mission_load_pct": totals["mission_pct"],
        "external_workshop_pct": totals["external_pct"],
        "theoretical_gap": totals["need"],
        "overstrength": totals["surplus"],
        "outside_ted": totals["outside_ted"],
        "ted_actual": totals["ted_actual"],
        "largest_category": category_analysis[0] if category_analysis else None,
        "largest_type": type_analysis[0] if type_analysis else None,
        "highest_need_model": model_analysis[0] if model_analysis and model_analysis[0]["need"] else None,
    }
    return templates.TemplateResponse(
        "equipment_numerical_status.html",
        {
            "request": request,
            "user": current_user,
            "hierarchy": hierarchy,
            "totals": totals,
            "category_analysis": category_analysis,
            "type_analysis": type_analysis,
            "model_analysis": model_analysis,
            "status_analysis": status_analysis,
            "analysis": analysis,
            "model_details": model_details,
        },
    )


@router.get("/equipment/{equipment_id}", response_class=HTMLResponse)
def equipment_detail_page(equipment_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    if not item: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return templates.TemplateResponse("equipment_detail.html", {"request": request, "item": item, "user": current_user})


@router.get("/equipment/{equipment_id}/edit", response_class=HTMLResponse)
def equipment_edit_page(equipment_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    if not item: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    types = type_services.list_types(db)
    return templates.TemplateResponse("equipment_edit.html", {"request": request, "item": item, "types": types, "user": current_user})


@router.post("/equipment/create")
def equipment_create_form(request: Request, equipment_type_id: int = Form(...), equipment_model_id: Optional[str] = Form(None), acquisition_document: str = Form(""), registration_number: str = Form(""), vin: str = Form(""), current_odometer: str = Form("0"), current_hours: str = Form("0"), technical_condition: str = Form("ready"), operational_status: str = Form("available"), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.create_equipment(db, EquipmentCreate(equipment_type_id=equipment_type_id, equipment_model_id=int(equipment_model_id) if equipment_model_id else None, acquisition_document=acquisition_document or None, registration_number=registration_number or None, vin=vin or None, current_odometer=current_odometer or 0, current_hours=current_hours or 0, technical_condition=technical_condition, operational_status=operational_status), user_id=current_user.id)
    except ValueError:
        pass
    return RedirectResponse(url="/equipment", status_code=status.HTTP_302_FOUND)


@router.post("/equipment/{equipment_id}/edit")
def equipment_edit_form(equipment_id: int, equipment_type_id: int = Form(...), equipment_model_id: Optional[str] = Form(None), acquisition_document: str = Form(""), registration_number: str = Form(""), vin: str = Form(""), acquisition_date: str = Form(""), technical_condition: str = Form("ready"), operational_status: str = Form("available"), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    if not item: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    try:
        date_value = datetime.strptime(acquisition_date, "%Y-%m-%d").date() if acquisition_date.strip() else None
        model_id = int(equipment_model_id) if equipment_model_id else None
        services.update_equipment(db, item, EquipmentUpdate(equipment_type_id=equipment_type_id, equipment_model_id=model_id, acquisition_document=acquisition_document or None, registration_number=registration_number or None, vin=vin or None, acquisition_date=date_value, technical_condition=technical_condition, operational_status=operational_status, notes=notes or None), user_id=current_user.id)
    except (ValueError, InvalidOperation) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "بيانات التعديل غير صحيحة")
    return RedirectResponse(url=f"/equipment/{equipment_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/equipment/{equipment_id}/delete")
def equipment_delete_form(equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_role(Role.ADMIN))):
    item = services.get_equipment(db, equipment_id)
    if item: services.delete_equipment(db, item)
    return RedirectResponse(url="/equipment", status_code=status.HTTP_302_FOUND)


@router.get("/equipment/{equipment_id}/meters", response_class=HTMLResponse)
def equipment_meters_page(equipment_id: int, request: Request, page: int = 1, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item, readings, total_readings, total_pages, current_page = meter_services.history_rows(db, equipment_id, page=page, page_size=20)
    if not item: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return templates.TemplateResponse("equipment_meters.html", {"request": request, "item": item, "readings": readings, "total_readings": total_readings, "total_pages": total_pages, "current_page": current_page, "user": current_user})


@router.post("/equipment/{equipment_id}/meters/create")
def equipment_meter_create(equipment_id: int, reading_date: str = Form(...), odometer: str = Form(""), hours: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    if not item: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    try:
        date_value = datetime.strptime(reading_date, "%Y-%m-%d")
        odometer_value = Decimal(odometer) if odometer.strip() else None
        hours_value = Decimal(hours) if hours.strip() else None
    except (ValueError, InvalidOperation):
        raise HTTPException(status_code=400, detail="تاريخ أو قيمة عداد غير صحيحة")
    if odometer_value is None and hours_value is None: raise HTTPException(status_code=400, detail="يجب إدخال قراءة الكيلومترات أو قراءة الساعات")
    try:
        meter_services.create_reading(db, equipment_id=equipment_id, odometer=odometer_value, hours=hours_value, reading_date=date_value, notes=notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/equipment/{equipment_id}/meters", status_code=status.HTTP_302_FOUND)


@router.post("/equipment/{equipment_id}/meters/{reading_id}/update")
def equipment_meter_update(equipment_id: int, reading_id: int, reading_date: str = Form(...), odometer: str = Form(""), hours: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    reading = db.query(MeterReading).filter(MeterReading.id == reading_id, MeterReading.equipment_id == equipment_id).first()
    if not item or not reading: raise HTTPException(status_code=404, detail="القراءة غير موجودة")
    try:
        date_value = datetime.strptime(reading_date, "%Y-%m-%d")
        unit = meter_services._unit(item); raw_value = odometer if unit == "km" else hours
        if not raw_value.strip(): raise ValueError("يجب إدخال قيمة العداد")
        value = meter_services._parse_decimal(raw_value)
    except (ValueError, InvalidOperation) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "تاريخ أو قيمة عداد غير صحيحة")
    if value < 0: raise HTTPException(status_code=400, detail="قيمة العداد لا يمكن أن تكون سالبة")
    if date_value.date() > datetime.now().date(): raise HTTPException(status_code=400, detail="لا يمكن إدخال قراءة بتاريخ مستقبلي")
    for existing in meter_services.list_readings(db, equipment_id):
        if existing.id == reading.id: continue
        existing_value = meter_services._value(existing, unit)
        if existing_value is None: continue
        existing_value = Decimal(existing_value)
        if existing.reading_date < date_value and existing_value > value: raise HTTPException(status_code=400, detail="قيمة القراءة الجديدة أقل من قراءة لاحقة مسجلة")
        if existing.reading_date > date_value and existing_value < value: raise HTTPException(status_code=400, detail="قيمة القراءة الجديدة أكبر من قراءة لاحقة مسجلة")
    reading.reading_date = date_value; reading.odometer = value if unit == "km" else None; reading.hours = value if unit == "hours" else None; reading.notes = (notes or "").strip()[:300] or None
    meter_services._refresh_equipment_current(db, item, unit); db.commit()
    return RedirectResponse(url=f"/equipment/{equipment_id}/meters", status_code=status.HTTP_302_FOUND)


@router.post("/equipment/{equipment_id}/meters/{reading_id}/delete")
def equipment_meter_delete(equipment_id: int, reading_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    reading = db.query(MeterReading).filter(MeterReading.id == reading_id, MeterReading.equipment_id == equipment_id).first()
    if not item or not reading: raise HTTPException(status_code=404, detail="القراءة غير موجودة")
    unit = meter_services._unit(item); old_value = meter_services._value(reading, unit)
    db.add(MeterReadingChange(reading_id=reading.id, equipment_id=equipment_id, changed_at=utc_now(), action="delete", source=reading.source or "manual", reading_date=reading.reading_date, unit=unit, old_value=old_value, new_value=None, actor_id=current_user.id, details="حذف قراءة مسجلة."))
    db.delete(reading); db.flush(); meter_services._refresh_equipment_current(db, item, unit); db.commit()
    return RedirectResponse(url=f"/equipment/{equipment_id}/meters", status_code=status.HTTP_302_FOUND)


@router.get("/api/equipment", response_model=list[EquipmentOut])
def api_list_equipment(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return services.list_equipment(db)


@router.get("/api/equipment/{equipment_id}", response_model=EquipmentOut)
def api_get_equipment(equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = services.get_equipment(db, equipment_id)
    if not item: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return item