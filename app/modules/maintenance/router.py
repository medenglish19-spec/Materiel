import base64
import binascii
import heapq
import json
from urllib.parse import urlencode
from datetime import date
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, delete
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_min_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import (MaintenanceOperation, MaintenanceModelOperation, MaintenanceOperationGroup, MaintenancePlan, MaintenancePlanOperation, MaintenanceRecord, maintenance_operation_models)
from app.modules.maintenance.models import MaintenanceCatalogImport
from app.modules.maintenance.catalog_import import (
    compare_previous_version, create_catalog_import, get_catalog_items, update_catalog_item,
)
from app.modules.maintenance.operation_excel_import import import_model_operations
from app.modules.maintenance.schemas import (MaintenanceModelOperationCreate, MaintenanceModelOperationOut, MaintenanceModelOperationUpdate, MaintenanceOperationBulkDelete, MaintenanceOperationCreate, MaintenanceOperationGroupCreate, MaintenanceOperationGroupOut, MaintenanceOperationGroupUpdate, MaintenanceOperationOut, MaintenanceOperationUpdate, MaintenanceOperationModelConditionSave, MaintenancePlanBulkDelete, MaintenancePlanCreate, MaintenancePlanOperationCreate, MaintenancePlanOperationsBulkCreate, MaintenancePlanOperationOut, MaintenancePlanOut, MaintenancePlanUpdate, MaintenanceRecordBulkDelete, MaintenanceRecordCreate, MaintenanceRecordOut, MaintenancePlanExecutionCreate)
from app.modules.maintenance.services import (
    CONDITION_UNSET,
    maintenance_record_has_execution_data,
    maintenance_record_delete_reason,
    chronology_error,
    contradiction_for,
    current_meter_value,
    effective_operations_for_equipment,
    latest_readings,
    latest_records,
    measurement_unit,
    priority_for,
    status_for,
    plan_status_for,
    effective_plans_for_equipment,
    latest_plan_records,
    validate_operation_applicable_to_equipment,
    operations_payload,
    operation_tasks_for_model,
    plan_condition,
    operation_reference,
    check_plan_operation_condition_compatibility,
    operation_condition_for_model,
    ModelCondition,
)
from app.modules.users.models import User
from app.modules.faults_repairs.models import Technician, Fault
from app.modules.faults_repairs.services import list_technicians
from app.modules.document_import.upload import read_upload_bytes, UploadTooLargeError
from app.modules.document_import.extraction.extractor import ExtractionError

router = APIRouter()
templates = get_module_templates("app/modules/maintenance/templates")
PERIODIC_PAGE_SIZE = 100
PeriodicSortKey = tuple[int, Decimal, int, str, int]


def _private_operation_payload(operation: MaintenanceModelOperation) -> dict:
    if operation.interval_km is not None:
        condition_text = f"{operation.interval_km:g} كم"
    elif operation.interval_hours is not None:
        condition_text = f"{operation.interval_hours:g} ساعة تشغيل"
    else:
        condition_text = f"{operation.interval_days} يوم"
    warning_text = "—"
    warning_parts = []
    if operation.warning_km is not None:
        warning_parts.append(f"{operation.warning_km:g} كم")
    if operation.warning_hours is not None:
        warning_parts.append(f"{operation.warning_hours:g} ساعة تشغيل")
    if operation.warning_days is not None:
        warning_parts.append(f"{operation.warning_days} يوم")
    if warning_parts:
        warning_text = " أو ".join(warning_parts)
    condition = {
        "model_id": operation.equipment_model_id,
        "model_name": operation.equipment_model.name if operation.equipment_model else None,
        "condition_source": "model",
        "is_defined": True,
        "interval_km": float(operation.interval_km) if operation.interval_km is not None else None,
        "interval_hours": float(operation.interval_hours) if operation.interval_hours is not None else None,
        "interval_days": operation.interval_days,
        "condition_text": condition_text,
        "unit_text": condition_text.split(" ", 1)[-1],
        "warning_text": warning_text,
    }
    return {
        "id": operation.id,
        "model_operation_id": operation.id,
        "operation_id": None,
        "source": "model",
        "equipment_model_id": operation.equipment_model_id,
        "name": operation.name,
        "description": operation.description,
        "group_id": operation.group_id,
        "interval_km": float(operation.interval_km) if operation.interval_km is not None else None,
        "interval_hours": float(operation.interval_hours) if operation.interval_hours is not None else None,
        "interval_days": operation.interval_days,
        "warning_km": float(operation.warning_km) if operation.warning_km is not None else None,
        "warning_hours": float(operation.warning_hours) if operation.warning_hours is not None else None,
        "warning_days": operation.warning_days,
        "is_active": operation.is_active,
        "model_conditions": [condition],
        "condition_summary": {
            "models_count": 1,
            "defined_count": 1,
            "unset_count": 0,
            "condition": condition_text,
            "condition_state": "shared",
            "warning": warning_text,
            "warning_state": "shared",
            "unit": condition["unit_text"],
            "has_multiple_conditions": False,
            "has_multiple_warnings": False,
        },
    }


def _operation_condition_mismatch(plan: MaintenancePlan, operation, db: Session) -> str | None:
    if isinstance(operation, MaintenanceModelOperation) or not hasattr(operation, "id"):
        condition = ModelCondition(
            condition_source="model",
            equipment_model_id=getattr(operation, "equipment_model_id", plan.equipment_model_id),
            interval_km=operation.interval_km,
            interval_hours=operation.interval_hours,
            interval_days=operation.interval_days,
        )
    else:
        condition = operation_condition_for_model(db, operation.id, plan.equipment_model_id)
        # Operations in the general library may have no model condition; those
        # retain the existing plan behavior and use the plan's cadence.
        if not condition.is_defined:
            return None
    return check_plan_operation_condition_compatibility(plan, condition)


def _plan_operation_payload(link: MaintenancePlanOperation) -> dict:
    is_private = link.model_operation_id is not None
    operation = link.model_operation if is_private else link.operation
    return {
        "id": link.id,
        "plan_id": link.plan_id,
        "operation_id": link.operation_id,
        "model_operation_id": link.model_operation_id,
        "source": "model" if is_private else "general",
        "operation_name": operation.name if operation else None,
        "sort_order": link.sort_order,
    }


def _operation_from_source(db: Session, *, source: str, operation_id: int):
    if source == "model":
        return db.get(MaintenanceModelOperation, operation_id)
    if source == "general":
        return db.get(MaintenanceOperation, operation_id)
    raise HTTPException(status_code=422, detail="مصدر عملية الصيانة غير صالح.")


def _plan_link_filter(source: str, operation_id: int):
    if source == "model":
        return MaintenancePlanOperation.model_operation_id == operation_id
    return MaintenancePlanOperation.operation_id == operation_id


def _parse_operation_form_reference(value: str) -> tuple[str, int]:
    raw = (value or "").strip()
    source, separator, raw_id = raw.partition(":")
    if not separator:
        source, raw_id = "general", raw
    if source not in {"general", "model"}:
        raise ValueError("مصدر عملية الصيانة غير صالح.")
    try:
        operation_id = int(raw_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("عملية الصيانة المحددة غير صالحة.") from exc
    if operation_id <= 0:
        raise ValueError("عملية الصيانة المحددة غير صالحة.")
    return source, operation_id


def _encode_periodic_cursor(sort_key: PeriodicSortKey) -> str:
    payload = [sort_key[0], str(sort_key[1]), sort_key[2], sort_key[3], sort_key[4]]
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")


def _decode_periodic_cursor(token: str | None) -> PeriodicSortKey | None:
    if not token:
        return None
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("utf-8")
        )
        if (
            not isinstance(payload, list)
            or len(payload) != 5
            or type(payload[0]) is not int
            or payload[0] not in {1, 2, 3, 4, 5}
            or not isinstance(payload[1], str)
            or type(payload[2]) is not int
            or not isinstance(payload[3], str)
            or type(payload[4]) is not int
            or payload[4] < 0
        ):
            raise ValueError
        remaining = Decimal(payload[1])
        if not remaining.is_finite():
            raise ValueError
        return payload[0], remaining, payload[2], payload[3], payload[4]
    except (binascii.Error, UnicodeDecodeError, InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="مؤشر صفحة الصيانة الدورية غير صالح.")


def _maintenance_status_counts(db: Session, equipment: list[Equipment]) -> dict[str, int]:
    """Count due/near maintenance separately from operations without a record."""
    readings = latest_readings(db)
    records = latest_records(db)
    tasks_by_model = {}
    counts = {"due": 0, "unrecorded": 0}
    for eq in equipment:
        model_id = eq.equipment_model_id
        if model_id is None:
            continue
        if model_id not in tasks_by_model:
            tasks_by_model[model_id] = operation_tasks_for_model(db, model_id)
        current_value = current_meter_value(eq, readings.get(eq.id))
        for task in tasks_by_model[model_id]:
            operation = task.operation
            state, _, _, _ = status_for(
                operation, eq, records.get((eq.id, *operation_reference(operation))), current_value,
                condition=task.condition,
            )
            if state in {"مستحقة الآن", "تقترب"}:
                counts["due"] += 1
            elif state == "بلا سجل":
                counts["unrecorded"] += 1
    return counts


@router.get("/maintenance/catalog-imports", response_class=HTMLResponse)
def maintenance_catalog_imports_page(
    request: Request, db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    models = db.query(EquipmentModel).options(joinedload(EquipmentModel.brand)).order_by(EquipmentModel.name).all()
    imports = db.query(MaintenanceCatalogImport).options(
        joinedload(MaintenanceCatalogImport.equipment_model),
    ).order_by(MaintenanceCatalogImport.created_at.desc(), MaintenanceCatalogImport.id.desc()).all()
    return templates.TemplateResponse(request=request, name="maintenance_catalog_imports.html", context={
        "request": request, "user": current_user, "models": models, "imports": imports,
    })


@router.post("/maintenance/catalog-imports")
async def maintenance_catalog_import_create(
    model_id: int = Form(...), file: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    from pathlib import Path
    filename = file.filename or ""
    try:
        data = await read_upload_bytes(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    try:
        record, duplicate = create_catalog_import(
            db, model_id=model_id, filename=filename, data=data, user_id=current_user.id if current_user else None,
        )
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    target = f"/maintenance/catalog-imports/{record.id}?duplicate=1" if duplicate else f"/maintenance/catalog-imports/{record.id}"
    return RedirectResponse(target, status_code=303)


@router.get("/maintenance/catalog-imports/{catalog_id}", response_class=HTMLResponse)
def maintenance_catalog_import_detail(
    catalog_id: int, request: Request, db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    record = db.query(MaintenanceCatalogImport).options(
        joinedload(MaintenanceCatalogImport.equipment_model),
    ).filter(MaintenanceCatalogImport.id == catalog_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="كتالوج الصيانة غير موجود.")
    all_items = get_catalog_items(record)
    query_text = request.query_params.get("q", "").strip()
    schedule_type = request.query_params.get("schedule_type", "").strip()
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    filtered_items = [
        (index, item) for index, item in enumerate(all_items)
        if (not schedule_type or item.get("schedule_type") == schedule_type)
        and (not query_text or query_text.casefold() in " ".join(str(item.get(key) or "") for key in (
            "operation_name", "section", "source_excerpt", "condition_note", "source_page",
        )).casefold())
    ]
    page_size = 40
    page_count = max(1, (len(filtered_items) + page_size - 1) // page_size)
    page = min(page, page_count)
    page_start = (page - 1) * page_size
    page_items = filtered_items[page_start:page_start + page_size]
    item_groups = []
    for schedule_key, schedule_label in (
        ("normal", "الجدول القياسي"),
        ("severe_conditions", "جدول الظروف القاسية"),
        ("unclassified", "عمليات غير مصنفة"),
    ):
        group_rows = [
            {"index": item_index, "item": item}
            for item_index, item in page_items
            if (
                item.get("schedule_type") == schedule_key
                if schedule_key != "unclassified"
                else item.get("schedule_type") not in {"normal", "severe_conditions"}
            )
        ]
        if group_rows:
            item_groups.append({"key": schedule_key, "label": schedule_label, "rows": group_rows})
    try:
        warnings = json.loads(record.warnings_json or "[]")
    except json.JSONDecodeError:
        warnings = ["تعذر قراءة تحذيرات الاستخراج."]
    return templates.TemplateResponse(request=request, name="maintenance_catalog_import_detail.html", context={
        "request": request, "user": current_user, "catalog": record,
        "items": [item for _, item in page_items],
        "item_indices": [index for index, _ in page_items],
        "item_groups": item_groups,
        "items_total": len(all_items), "filtered_total": len(filtered_items),
        "page": page, "page_count": page_count, "page_start": page_start,
        "query_text": query_text, "schedule_type_filter": schedule_type,
        "normal_count": sum(item.get("schedule_type") == "normal" for item in all_items),
        "severe_count": sum(item.get("schedule_type") == "severe_conditions" for item in all_items),
        "pending_count": sum(item.get("review_state") == "needs_review" for item in all_items),
        "warnings": warnings, "version_diff": compare_previous_version(db, record),
        "operation_groups": db.query(MaintenanceOperationGroup).order_by(MaintenanceOperationGroup.sort_order, MaintenanceOperationGroup.name).all(),
        "duplicate": request.query_params.get("duplicate") == "1",
    })


@router.post("/maintenance/catalog-imports/{catalog_id}/items/{item_index}")
async def maintenance_catalog_item_update(
    catalog_id: int, item_index: int, request: Request, db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    record = db.get(MaintenanceCatalogImport, catalog_id)
    if record is None:
        raise HTTPException(status_code=404, detail="كتالوج الصيانة غير موجود.")
    if record.status == "applied":
        raise HTTPException(status_code=409, detail="تم تطبيق هذا الإصدار؛ لا يمكن تغيير مصدره بعد الاعتماد.")
    form = await request.form()
    changes = {
        "operation_name": str(form.get("operation_name", "")),
        "review_state": str(form.get("review_state", "needs_review")),
        "review_note": str(form.get("review_note", "")),
        "schedule_type": str(form.get("schedule_type", "unclassified")),
    }
    raw_condition = str(form.get("corrected_condition", "")).strip()
    if raw_condition:
        try:
            changes["corrected_condition"] = json.loads(raw_condition)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="شرط الصيانة يجب أن يكون JSON صالحًا.") from exc
    else:
        changes["corrected_condition"] = None
    changes["condition_note"] = str(form.get("condition_note", "")).strip() or None
    raw_group_id = str(form.get("group_id", "")).strip()
    if raw_group_id:
        try:
            group_id = int(raw_group_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="تصنيف العملية غير صالح.") from exc
        if db.get(MaintenanceOperationGroup, group_id) is None:
            raise HTTPException(status_code=422, detail="تصنيف العملية المحدد غير موجود.")
        changes["group_id"] = group_id
    else:
        changes["group_id"] = None
    try:
        update_catalog_item(db, record, item_index, changes)
    except (IndexError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    query = {key: value for key, value in {
        "page": request.query_params.get("page"),
        "q": request.query_params.get("q"),
        "schedule_type": request.query_params.get("schedule_type"),
    }.items() if value not in (None, "")}
    suffix = f"?{urlencode(query)}" if query else ""
    return RedirectResponse(f"/maintenance/catalog-imports/{catalog_id}{suffix}#item-{item_index}", status_code=303)


@router.post("/maintenance/catalog-imports/{catalog_id}/review-selection")
async def maintenance_catalog_review_selection(
    catalog_id: int, request: Request, db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    record = db.get(MaintenanceCatalogImport, catalog_id)
    if record is None:
        raise HTTPException(status_code=404, detail="كتالوج الصيانة غير موجود.")
    if record.status == "applied":
        raise HTTPException(status_code=409, detail="تم تطبيق هذا الإصدار؛ لا يمكن تغيير مراجعته.")
    form = await request.form()
    try:
        indices = [int(value) for value in form.getlist("item_indices")]
        review_state = str(form.get("review_state", ""))
        if not indices:
            raise ValueError("حدد صفًا واحدًا على الأقل.")
        if review_state not in {"accepted", "rejected"}:
            raise ValueError("قرار المراجعة غير صالح.")
        items = get_catalog_items(record)
        if len(set(indices)) != len(indices) or any(index < 0 or index >= len(items) for index in indices):
            raise ValueError("تتضمن قائمة المراجعة صفًا غير صالح.")
        for index in indices:
            item = items[index]
            if review_state == "accepted":
                if item.get("schedule_type") not in {"normal", "severe_conditions"}:
                    raise ValueError("لا يمكن قبول صف غير مصنف كعملية أساسية أو إضافية.")
                if not item.get("corrected_condition") and not item.get("condition_note"):
                    raise ValueError(f"أدخل شرطًا أساسيًا أو وصفًا للصف: {item.get('operation_name', '')}.")
            item["review_state"] = review_state
        record.items_json = json.dumps(items, ensure_ascii=False)
        record.status = "draft"
        record.reviewed_at = None
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    query = {key: value for key, value in {
        "page": form.get("page"), "q": form.get("q"),
        "schedule_type": form.get("schedule_type"),
    }.items() if value not in (None, "")}
    suffix = f"?{urlencode(query)}" if query else ""
    return RedirectResponse(f"/maintenance/catalog-imports/{catalog_id}{suffix}", status_code=303)


@router.post("/maintenance/catalog-imports/{catalog_id}/apply")
def maintenance_catalog_apply(
    catalog_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    record = db.get(MaintenanceCatalogImport, catalog_id)
    if record is None:
        raise HTTPException(status_code=404, detail="كتالوج الصيانة غير موجود.")
    if record.status == "applied":
        raise HTTPException(status_code=409, detail="سبق تطبيق هذا الإصدار على مكتبة العمليات.")
    items = get_catalog_items(record)
    accepted = [(index, item) for index, item in enumerate(items) if item.get("review_state") == "accepted"]
    if not accepted:
        raise HTTPException(status_code=422, detail="اقبل عملية واحدة على الأقل بعد مراجعتها.")
    if any(item.get("schedule_type") in {"normal", "severe_conditions"} and item.get("review_state") == "needs_review" for item in items):
        raise HTTPException(status_code=422, detail="أكمل مراجعة العمليات المستخرجة أو ارفض الصفوف غير المناسبة قبل التطبيق.")
    if any(not item.get("corrected_condition") and not item.get("condition_note") for _, item in accepted):
        raise HTTPException(status_code=422, detail="أدخل الشرط الأساسي أو وصف الشرط لكل عملية مقبولة قبل التطبيق.")
    # Apply in one transaction. This only creates/links maintenance operations;
    # it never edits an approved plan or an execution record.
    try:
        for item_index, item in accepted:
            if item.get("schedule_type") not in {"normal", "severe_conditions"}:
                raise ValueError("لا يمكن تطبيق صف غير مصنف كعملية أساسية أو إضافية.")
            name = item["operation_name"].strip()
            condition = item.get("corrected_condition") or {}
            schedule_label = "الجدول القياسي" if item.get("schedule_type") == "normal" else "جدول الظروف القاسية"
            interval_source = item.get("source_interval", {}).get("raw")
            variant_description = " | ".join(filter(None, [
                f"سياق الجدول: {schedule_label}",
                f"فاصل المصدر: {interval_source}" if interval_source else None,
                f"صف المصدر: {item.get('source_page') or 'غير محدد'}",
            ]))
            variant_match_key = " | ".join(filter(None, [
                f"سياق الجدول: {schedule_label}",
                f"فاصل المصدر: {interval_source}" if interval_source else None,
            ]))
            group_id = item.get("group_id")
            if group_id is None:
                group = db.query(MaintenanceOperationGroup).filter(
                    MaintenanceOperationGroup.name == "عمليات مستوردة من كتالوجات الصيانة"
                ).first()
                if group is None:
                    group = MaintenanceOperationGroup(name="عمليات مستوردة من كتالوجات الصيانة", sort_order=999)
                    db.add(group)
                    db.flush()
                group_id = group.id
            # Catalog entries belong to the model-private library. Keep distinct
            # schedule profiles as distinct rows even when their operation names match.
            candidates = db.query(MaintenanceModelOperation).filter(
                MaintenanceModelOperation.equipment_model_id == record.equipment_model_id,
                MaintenanceModelOperation.name.ilike(name),
            ).all()
            op_row = None
            for candidate in candidates:
                if variant_match_key not in (candidate.description or ""):
                    continue
                same_condition = all(
                    getattr(candidate, column) == condition.get(key)
                    for column, key in (
                        ("interval_km", "interval_km"),
                        ("interval_hours", "interval_hours"),
                        ("interval_days", "interval_days"),
                    )
                )
                if same_condition:
                    op_row = candidate
                    break
            if op_row is None:
                op_row = MaintenanceModelOperation(
                    name=name, group_id=group_id,
                    equipment_model_id=record.equipment_model_id,
                    description="\n".join(filter(None, [
                        f"استورد من {record.document_title or record.filename}، الإصدار {record.version_number}، الصفحة {item.get('source_page') or 'غير محددة'}.",
                        item.get("condition_note"),
                        f"مقطع المصدر: {item.get('source_excerpt')}" if item.get("source_excerpt") else None,
                        variant_description,
                    ])),
                    is_active=True,
                )
                db.add(op_row)
                db.flush()
            approved_membership = db.query(MaintenancePlanOperation.id).join(
                MaintenancePlan, MaintenancePlan.id == MaintenancePlanOperation.plan_id,
            ).filter(
                MaintenancePlan.equipment_model_id == record.equipment_model_id,
                MaintenancePlanOperation.model_operation_id == op_row.id,
                MaintenancePlan.is_active.is_(True), MaintenancePlan.is_approved.is_(True),
            ).first()
            if approved_membership:
                raise ValueError(f"العملية «{name}» مرتبطة بخطة معتمدة للطراز؛ لم يُغيّر الشرط.")
            op_row.interval_km = condition.get("interval_km")
            op_row.interval_hours = condition.get("interval_hours")
            op_row.interval_days = condition.get("interval_days")
            item["model_operation_id"] = op_row.id
        record.items_json = json.dumps(items, ensure_ascii=False)
        record.status = "applied"
        record.reviewed_at = datetime.utcnow()
        record.reviewed_by_id = current_user.id if current_user else None
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(f"/maintenance/catalog-imports/{catalog_id}", status_code=303)


def _sync_operation_model_conditions(db: Session, operation, submitted: list) -> None:
    """Write the submitted per-model conditions of one operation.

    Each relation row is written on its own, so changing one model's condition
    cannot alter another model's row. Models absent from the payload lose their
    relation row; models present in both keep their existing row.
    """
    from app.modules.maintenance.schemas import MaintenanceOperationModelConditionIn
    by_model = {}
    for index, item in enumerate(submitted):
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        model_id = data.pop("model_id")
        if model_id in by_model:
            raise HTTPException(status_code=400, detail="نموذج مكرر أكثر من مرة في نفس العملية.")
        if db.get(EquipmentModel, model_id) is None:
            raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
        by_model[model_id] = (index, data)

    existing = {
        row.equipment_model_id: row
        for row in db.execute(
            maintenance_operation_models.select().where(
                maintenance_operation_models.c.operation_id == operation.id
            )
        ).all()
    }

    for model_id in list(existing):
        if model_id not in by_model:
            db.execute(
                delete(maintenance_operation_models).where(
                    maintenance_operation_models.c.operation_id == operation.id,
                    maintenance_operation_models.c.equipment_model_id == model_id,
                )
            )

    for model_id, (_, data) in by_model.items():
        row = existing.get(model_id)
        if row is None:
            db.execute(
                maintenance_operation_models.insert().values(
                    operation_id=operation.id, equipment_model_id=model_id, **data
                )
            )
        else:
            db.execute(
                maintenance_operation_models.update()
                .where(
                    maintenance_operation_models.c.operation_id == operation.id,
                    maintenance_operation_models.c.equipment_model_id == model_id,
                )
                .values(**data)
            )

    db.expire(operation, ["equipment_models"])


def _delete_plan(db: Session, plan: MaintenancePlan) -> None:
    """Delete a plan only when it has no records with actual execution data."""
    plan_records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.plan_id == plan.id
    ).all()
    if any(maintenance_record_has_execution_data(record) for record in plan_records):
        raise ValueError("لا يمكن حذف الخطة لارتباطها بسجلات تنفيذ تاريخية.")
    db.query(MaintenancePlanOperation).filter(
        MaintenancePlanOperation.plan_id == plan.id
    ).delete(synchronize_session=False)
    db.delete(plan)


@router.get("/maintenance", response_class=HTMLResponse)
def maintenance_dashboard_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="maintenance_home.html", context={"request": request, "user": current_user})


@router.get("/maintenance/periodic", response_class=HTMLResponse)
def periodic_maintenance_page(
    request: Request,
    q: str = Query(default="", max_length=100),
    state_filter: str = Query(default="", alias="state"),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if after and before:
        raise HTTPException(status_code=400, detail="يجب تحديد اتجاه واحد للتنقل بين صفحات الصيانة.")
    allowed_states = {"", "مستحقة الآن", "تقترب", "ضمن الموعد", "بلا سجل", "الشرط غير محدد"}
    if state_filter not in allowed_states:
        raise HTTPException(status_code=422, detail="حالة الصيانة المحددة غير صالحة.")
    after_key = _decode_periodic_cursor(after)
    before_key = _decode_periodic_cursor(before)
    search = q.strip().casefold()
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.asset_code).all()
    readings = latest_readings(db); records = latest_records(db)
    counts = {"total": 0, "danger": 0, "warning": 0, "success": 0, "neutral": 0}
    tasks_by_model = {}
    model_ids = {eq.equipment_model_id for eq in equipment if eq.equipment_model_id is not None}
    approved_model_ids = {
        model_id for (model_id,) in db.query(MaintenancePlan.equipment_model_id).filter(
            MaintenancePlan.equipment_model_id.in_(model_ids or {-1}),
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        ).distinct().all()
    }
    unapproved_models = sorted({
        eq.equipment_model.name
        for eq in equipment
        if eq.equipment_model_id is not None
        and eq.equipment_model is not None
        and eq.equipment_model_id not in approved_model_ids
    })
    filtered_total = 0
    row_index = 0

    def matching_rows():
        nonlocal filtered_total, row_index
        for eq in equipment:
            current_value = current_meter_value(eq, readings.get(eq.id))
            model_id = eq.equipment_model_id
            if model_id is not None and model_id not in tasks_by_model:
                tasks_by_model[model_id] = operation_tasks_for_model(db, model_id)
            for task in tasks_by_model.get(model_id, []):
                operation = task.operation
                rec = records.get((eq.id, *operation_reference(operation)))
                # العمليات التابعة للخطة تُقاس بشرط خطتها؛ والعملية المستقلة بشرط طرازها.
                state, css, remaining, meta = status_for(
                    operation, eq, rec, current_value, condition=task.condition
                )
                counts["total"] += 1
                counts[css] += 1
                current_index = row_index
                row_index += 1

                registration = eq.registration_number or eq.vin or ""
                condition_unset = task.condition.condition_source == CONDITION_UNSET
                if state_filter == "الشرط غير محدد" and not condition_unset:
                    continue
                if state_filter and state_filter != "الشرط غير محدد" and state != state_filter:
                    continue
                if search and search not in " ".join(
                    value for value in (registration, eq.asset_code or "") if value
                ).casefold():
                    continue

                filtered_total += 1
                sort_key = (
                    priority_for(state, remaining, meta),
                    remaining if remaining is not None else Decimal("999999999"),
                    meta.get("remaining_days") if meta.get("remaining_days") is not None else 999999999,
                    eq.registration_number or eq.asset_code or "",
                    current_index,
                )
                if after_key is not None and sort_key <= after_key:
                    continue
                if before_key is not None and sort_key >= before_key:
                    continue
                row = {
                    "equipment": eq,
                    "operation": operation,
                    "record": rec,
                    "current": current_value,
                    "unit": measurement_unit(eq),
                    "next_meter": meta.get("next_meter"),
                    "next_date": meta.get("next_date"),
                    "remaining": remaining,
                    "remaining_days": meta.get("remaining_days"),
                    "state": state,
                    "css": css,
                    "priority": sort_key[0],
                    "condition_unset": condition_unset,
                    "contradiction": contradiction_for(eq, rec, current_value, db),
                    "plan": task.plan,
                }
                yield sort_key, row

    if before_key is not None:
        candidates = heapq.nlargest(
            PERIODIC_PAGE_SIZE + 1, matching_rows(), key=lambda item: item[0]
        )
        has_previous = len(candidates) > PERIODIC_PAGE_SIZE
        selected = list(reversed(candidates[:PERIODIC_PAGE_SIZE]))
        has_next = bool(selected)
    else:
        candidates = heapq.nsmallest(
            PERIODIC_PAGE_SIZE + 1, matching_rows(), key=lambda item: item[0]
        )
        selected = candidates[:PERIODIC_PAGE_SIZE]
        has_previous = after_key is not None and bool(selected)
        has_next = len(candidates) > PERIODIC_PAGE_SIZE

    rows = [row for _, row in selected]
    previous_cursor = _encode_periodic_cursor(selected[0][0]) if has_previous else None
    next_cursor = _encode_periodic_cursor(selected[-1][0]) if has_next else None
    base_url = request.url.remove_query_params("after").remove_query_params("before")
    previous_url = (
        str(base_url.include_query_params(before=previous_cursor, q=q, state=state_filter))
        if previous_cursor
        else None
    )
    next_url = (
        str(base_url.include_query_params(after=next_cursor, q=q, state=state_filter))
        if next_cursor
        else None
    )
    return templates.TemplateResponse(
        request=request,
        name="maintenance_dashboard.html",
        context={
            "request": request,
            "user": current_user,
            "rows": rows,
            "counts": counts,
            "unapproved_models": unapproved_models,
            "query": q,
            "state_filter": state_filter,
            "filtered_total": filtered_total,
            "previous_url": previous_url,
            "next_url": next_url,
        },
    )


@router.get("/maintenance/plans", response_class=HTMLResponse)
def maintenance_plans_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    models = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.brand),
        joinedload(EquipmentModel.equipment_type),
    ).order_by(EquipmentModel.name).all()
    model_options = [{"id": model.id, "name": model.name} for model in models]
    # Build operation conditions for the template as a dict with composite keys
    operations = db.query(MaintenanceOperation).order_by(
        MaintenanceOperation.name, MaintenanceOperation.id,
    ).all()
    operation_conditions_list = operations_payload(db, operations)
    # Transform to dict with keys like "operation_id:model_id"
    operation_conditions = {}
    for op in operation_conditions_list:
        for mc in op.get("model_conditions", []):
            key = f"{op['id']}:{mc['model_id']}"
            operation_conditions[key] = mc
    return templates.TemplateResponse(
        request=request, name="maintenance_plans.html", context={"request": request, "user": current_user, "models": model_options, "operation_conditions": operation_conditions},
    )

@router.get("/maintenance/rules", response_class=HTMLResponse)
def maintenance_rules_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    models = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.brand),
        joinedload(EquipmentModel.equipment_type),
    ).order_by(EquipmentModel.name).all()
    imported_model_name = None
    try:
        imported_model_id = int(request.query_params.get("model_id", ""))
    except (TypeError, ValueError):
        imported_model_id = None
    if imported_model_id is not None:
        imported_model = db.get(EquipmentModel, imported_model_id)
        if imported_model is not None:
            imported_model_name = imported_model.name
    selected_library_model_id = request.query_params.get("view_model_id") or request.query_params.get("model_id") or ""
    return templates.TemplateResponse(
        request=request, name="maintenance_rules_model_only.html", context={
            "request": request, "user": current_user, "models": models,
            "imported_count": request.query_params.get("imported"),
            "imported_model_name": imported_model_name,
            "selected_library_model_id": selected_library_model_id,
            "import_error": request.query_params.get("import_error"),
        },
    )


@router.post("/maintenance/rules/import")
async def maintenance_operation_import(
    model_id: int = Form(...), file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".xlsx"):
        return RedirectResponse(
            f"/maintenance/rules?{urlencode({'import_error': 'ارفع ملف Excel بصيغة .xlsx.', 'model_id': model_id})}",
            status_code=303,
        )
    try:
        data = await read_upload_bytes(file)
        imported_count = import_model_operations(db, model_id=model_id, data=data)
    except UploadTooLargeError as exc:
        message = str(exc)
        return RedirectResponse(
            f"/maintenance/rules?{urlencode({'import_error': message, 'model_id': model_id})}", status_code=303,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/maintenance/rules?{urlencode({'import_error': str(exc), 'model_id': model_id})}", status_code=303,
        )
    return RedirectResponse(
        f"/maintenance/rules?{urlencode({'imported': imported_count, 'model_id': model_id})}",
        status_code=303,
    )

@router.get("/maintenance/records", response_class=HTMLResponse)
def maintenance_records_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    can_manage_records = settings.DEV_DISABLE_AUTH or current_user.role in {
        Role.ADMIN.value,
        Role.FLEET_MANAGER.value,
    }
    records = db.query(MaintenanceRecord).options(
        joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_type),
        joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_model),
        joinedload(MaintenanceRecord.operation),
        joinedload(MaintenanceRecord.model_operation),
        joinedload(MaintenanceRecord.plan),
        joinedload(MaintenanceRecord.technician),
    ).order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)).all()
    equipment = db.query(Equipment).options(
        joinedload(Equipment.equipment_type),
        joinedload(Equipment.equipment_model),
    ).order_by(Equipment.registration_number, Equipment.asset_code).all()
    maintenance_counts = _maintenance_status_counts(db, equipment)
    model_ids = {eq.equipment_model_id for eq in equipment if eq.equipment_model_id is not None}
    approved_model_ids = {
        model_id for (model_id,) in db.query(MaintenancePlan.equipment_model_id).filter(
            MaintenancePlan.equipment_model_id.in_(model_ids or {-1}),
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        ).distinct().all()
    }
    unapproved_model_rows = sorted({
        (eq.equipment_model_id, eq.equipment_model.name)
        for eq in equipment
        if eq.equipment_model_id is not None
        and eq.equipment_model is not None
        and eq.equipment_model_id not in approved_model_ids
    }, key=lambda item: (item[1], item[0]))

    general_operations = db.query(MaintenanceOperation).filter(
        MaintenanceOperation.is_active.is_(True)
    ).order_by(MaintenanceOperation.name, MaintenanceOperation.id).all()
    model_operations = db.query(MaintenanceModelOperation).filter(
        MaintenanceModelOperation.is_active.is_(True)
    ).order_by(MaintenanceModelOperation.name, MaintenanceModelOperation.id).all()
    operations = [
        {"id": operation.id, "source": "general", "value": f"general:{operation.id}", "name": operation.name}
        for operation in general_operations
    ] + [
        {"id": operation.id, "source": "model", "value": f"model:{operation.id}", "name": operation.name}
        for operation in model_operations
    ]
    plans = db.query(MaintenancePlan).filter(
        MaintenancePlan.is_active.is_(True),
        MaintenancePlan.is_approved.is_(True),
    ).order_by(MaintenancePlan.name, MaintenancePlan.id).all()

    # الفنيون الفعليون من الورشة الداخلية (لا قائمة ثابتة ولا أسماء تجريبية).
    technicians = list_technicians(db, active_only=True)

    edit_record = None
    edit_id = request.query_params.get("edit")
    if can_manage_records and edit_id and edit_id.isdigit():
        edit_record = db.query(MaintenanceRecord).options(
            joinedload(MaintenanceRecord.operation),
            joinedload(MaintenanceRecord.model_operation),
            joinedload(MaintenanceRecord.plan),
        ).filter(MaintenanceRecord.id == int(edit_id)).first()

    # مؤهّل العملية يُحدَّد بطراز العتاد وحده عبر علاقة العملية بالطراز في
    # maintenance_operation_models. لا تُدرَج العمليات المستقلة/العامة غير
    # المرتبطة بأي طراز، لأنها غير قابلة للتنفيذ على عتاد محدد.
    operation_model_ids = {
        f"general:{operation.id}": ",".join(
            str(model.id)
            for model in sorted(operation.equipment_models, key=lambda model: model.id)
        )
        for operation in general_operations
    }
    operation_model_ids.update({f"model:{operation.id}": str(operation.equipment_model_id) for operation in model_operations})

    # Compute meter_required_by_operation: for each operation, check its model conditions
    # to determine if a meter reading is required for each model
    from app.modules.maintenance.services import operation_conditions_by_model, meter_required_for_condition
    meter_required_by_operation = {}
    for operation in general_operations:
        # Get all model conditions for this operation (including unset ones)
        conditions = operation_conditions_by_model(db, [operation.id])
        required_by_model = []
        for (op_id, model_id), condition in conditions.items():
            if op_id == operation.id:
                unit = "km"  # Default, but we check both km and hours
                required = meter_required_for_condition(condition, "km") or meter_required_for_condition(condition, "hours")
                required_by_model.append(f"{model_id}:{'1' if required else '0'}")
        # Also include models that are linked to the operation but have no condition row (unset)
        for model in operation.equipment_models:
            if (operation.id, model.id) not in conditions:
                required_by_model.append(f"{model.id}:0")
        meter_required_by_operation[f"general:{operation.id}"] = ",".join(required_by_model)
    for operation in model_operations:
        meter_required_by_operation[f"model:{operation.id}"] = (
            f"{operation.equipment_model_id}:1"
            if operation.interval_km is not None or operation.interval_hours is not None
            else f"{operation.equipment_model_id}:0"
        )

    plan_equipment_ids = {}
    for plan in plans:
        plan_equipment_ids.setdefault(plan.id, set()).add(plan.equipment_model_id)
    return templates.TemplateResponse(
        request=request, name="maintenance_records.html", context={
            "request": request,
            "user": current_user,
            "records": records,
            "equipment": equipment,
            "due_count": maintenance_counts["due"],
            "unrecorded_count": maintenance_counts["unrecorded"],
            "unapproved_model_rows": unapproved_model_rows,
            "operations": operations,
            "plans": plans,
            "technicians": technicians,
            "operation_model_ids": operation_model_ids,
            "meter_required_by_operation": meter_required_by_operation,
            "edit_record": edit_record,
            "can_manage_records": can_manage_records,
        },
    )


@router.post("/maintenance/records/create")
def maintenance_record_create(
    equipment_id: int = Form(...),
    operation_id: str = Form(...),
    plan_id: int | None = Form(None),
    maintenance_date: date = Form(...),
    meter_value: str = Form(""),
    work_order: str = Form(""),
    workshop: str = Form(""),
    technician_id: int | None = Form(None),
    description: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    records_url = "/maintenance/records"
    equipment = db.query(Equipment).options(
        joinedload(Equipment.equipment_type),
        joinedload(Equipment.equipment_model),
    ).filter(Equipment.id == equipment_id).first()
    if equipment is None:
        return RedirectResponse(f"{records_url}?error=equipment", status_code=status.HTTP_303_SEE_OTHER)

    try:
        operation_source, operation_pk = _parse_operation_form_reference(operation_id)
    except ValueError:
        return RedirectResponse(f"{records_url}?error=operation_not_found", status_code=status.HTTP_303_SEE_OTHER)
    operation = _operation_from_source(db, source=operation_source, operation_id=operation_pk)
    if operation is not None and not operation.is_active:
        operation = None
    if operation is None:
        return RedirectResponse(f"{records_url}?error=operation_not_found", status_code=status.HTTP_303_SEE_OTHER)

    # Validate operation applicability to equipment using shared function
    validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
    if validation_error:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    if operation_reference(operation) not in {
        operation_reference(item) for item in effective_operations_for_equipment(db, equipment)
    }:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    plan = None
    if plan_id is not None:
        plan = db.query(MaintenancePlan).filter(
            MaintenancePlan.id == plan_id,
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
            MaintenancePlan.equipment_model_id == equipment.equipment_model_id,
        ).first()
        if plan is None:
            return RedirectResponse(f"{records_url}?error=plan_model", status_code=status.HTTP_303_SEE_OTHER)
        linked = db.query(MaintenancePlanOperation.id).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            _plan_link_filter(operation_source, operation.id),
        ).first()
        if linked is None:
            return RedirectResponse(f"{records_url}?error=plan_operation", status_code=status.HTTP_303_SEE_OTHER)

    if maintenance_date > date.today():
        return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)

    work_order_clean = work_order.strip()
    if work_order_clean and not work_order_clean.isdigit():
        return RedirectResponse(f"{records_url}?error=work_order", status_code=status.HTTP_303_SEE_OTHER)

    technician = None
    if technician_id is not None:
        technician = db.query(Technician).filter(Technician.id == technician_id).first()
        if technician is None or not technician.is_active:
            return RedirectResponse(f"{records_url}?error=technician", status_code=status.HTTP_303_SEE_OTHER)

    unit = measurement_unit(equipment)
    meter = None
    if meter_value:
        try:
            meter = Decimal(meter_value)
        except (InvalidOperation, ValueError):
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0:
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)

    from app.modules.maintenance.services import operation_condition_for_model, meter_required_for_condition
    condition = (
        plan_condition(plan) if plan is not None else
        ModelCondition(condition_source="model", equipment_model_id=operation.equipment_model_id,
                       interval_km=operation.interval_km, interval_hours=operation.interval_hours,
                       interval_days=operation.interval_days)
        if operation_source == "model" else
        operation_condition_for_model(db, operation.id, equipment.equipment_model_id)
    )
    if meter_required_for_condition(condition, unit) and meter is None:
        return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)

    chronology = chronology_error(db, equipment_id, maintenance_date, meter)
    if chronology:
        return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)

    rec = MaintenanceRecord(
        equipment_id=equipment_id,
        operation_id=operation.id if operation_source == "general" else None,
        model_operation_id=operation.id if operation_source == "model" else None,
        plan_id=plan.id if plan is not None else None,
        maintenance_date=maintenance_date,
        meter_value=meter,
        work_order=work_order_clean or None,
        workshop=workshop.strip() or None,
        technician_id=technician.id if technician is not None else None,
        description=description.strip() or None,
        note=note.strip() or None,
        status="completed",
        created_by_id=current_user.id if current_user else None,
    )
    db.add(rec)
    try:
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"{records_url}?error=validation", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"{records_url}?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/update")
def maintenance_record_update(
    record_id: int,
    equipment_id: int = Form(...),
    operation_id: str = Form(...),
    plan_id: int | None = Form(None),
    maintenance_date: date = Form(...),
    meter_value: str = Form(""),
    work_order: str = Form(""),
    workshop: str = Form(""),
    technician_id: int | None = Form(None),
    description: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    records_url = "/maintenance/records"
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    equipment = db.query(Equipment).options(
        joinedload(Equipment.equipment_type),
        joinedload(Equipment.equipment_model),
    ).filter(Equipment.id == equipment_id).first()
    try:
        operation_source, operation_pk = _parse_operation_form_reference(operation_id)
    except ValueError:
        return RedirectResponse(f"{records_url}?error=operation_not_found", status_code=status.HTTP_303_SEE_OTHER)
    operation = _operation_from_source(db, source=operation_source, operation_id=operation_pk)
    if operation is not None and not operation.is_active:
        operation = None
    if rec is None or equipment is None or operation is None:
        return RedirectResponse(f"{records_url}?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # Validate operation applicability to equipment using shared function
    validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
    if validation_error:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    if operation_reference(operation) not in {operation_reference(item) for item in effective_operations_for_equipment(db, equipment)}:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    plan = None
    if plan_id is not None:
        plan = db.query(MaintenancePlan).filter(
            MaintenancePlan.id == plan_id,
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
            MaintenancePlan.equipment_model_id == equipment.equipment_model_id,
        ).first()
        if plan is None:
            return RedirectResponse(f"{records_url}?error=plan_model", status_code=status.HTTP_303_SEE_OTHER)
        linked = db.query(MaintenancePlanOperation.id).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            _plan_link_filter(operation_source, operation.id),
        ).first()
        if linked is None:
            return RedirectResponse(f"{records_url}?error=plan_operation", status_code=status.HTTP_303_SEE_OTHER)

    if maintenance_date > date.today():
        return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)

    work_order_clean = work_order.strip()
    if work_order_clean and not work_order_clean.isdigit():
        return RedirectResponse(f"{records_url}?error=work_order", status_code=status.HTTP_303_SEE_OTHER)

    technician = None
    if technician_id is not None:
        technician = db.query(Technician).filter(Technician.id == technician_id).first()
        if technician is None or not technician.is_active:
            return RedirectResponse(f"{records_url}?error=technician", status_code=status.HTTP_303_SEE_OTHER)

    meter = None
    if meter_value:
        try:
            meter = Decimal(meter_value)
        except (InvalidOperation, ValueError):
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0:
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)

    unit = measurement_unit(equipment)
    from app.modules.maintenance.services import operation_condition_for_model, meter_required_for_condition
    condition = (
        plan_condition(plan) if plan is not None else
        ModelCondition(condition_source="model", equipment_model_id=operation.equipment_model_id,
                       interval_km=operation.interval_km, interval_hours=operation.interval_hours,
                       interval_days=operation.interval_days)
        if operation_source == "model" else
        operation_condition_for_model(db, operation.id, equipment.equipment_model_id)
    )
    if meter_required_for_condition(condition, unit) and meter is None:
        return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)

    chronology = chronology_error(db, equipment_id, maintenance_date, meter, exclude_id=record_id)
    if chronology:
        return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)

    rec.equipment_id = equipment_id
    rec.operation_id = operation.id if operation_source == "general" else None
    rec.model_operation_id = operation.id if operation_source == "model" else None
    rec.plan_id = plan.id if plan is not None else None
    rec.maintenance_date = maintenance_date
    rec.meter_value = meter
    rec.work_order = work_order_clean or None
    rec.workshop = workshop.strip() or None
    rec.technician_id = technician.id if technician is not None else None
    rec.description = description.strip() or None
    rec.note = note.strip() or None
    try:
        db.commit()
    except ValueError:
        db.rollback()
        return RedirectResponse(f"{records_url}?error=validation", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"{records_url}?saved=updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/delete")
def maintenance_record_delete(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if rec is None: return RedirectResponse("/maintenance/records?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    if maintenance_record_delete_reason(rec):
        return RedirectResponse("/maintenance/records?error=protected_record", status_code=status.HTTP_303_SEE_OTHER)
    db.delete(rec)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف سجل الصيانة.") from exc
    return RedirectResponse("/maintenance/records?changed=deleted", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/maintenance/records/{record_id}/delete-impact")
def maintenance_record_delete_impact(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    rec = db.get(MaintenanceRecord, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود")
    fault_count = db.query(Fault.id).filter(Fault.maintenance_record_id == rec.id).count()
    reason = maintenance_record_delete_reason(rec)
    effects = [
        {"label": "سجل الصيانة", "count": 1},
        {"label": "الأعطال التي ستبقى مع فصل ارتباطها بسجل الصيانة", "count": fault_count, "kind": "unlink"},
        {"label": "قيمة العداد الحالية ستعاد مزامنتها من السجلات المتبقية", "count": 1, "kind": "recalculate"},
    ]
    return {"label": f"{rec.maintenance_date} — {rec.operation.name if rec.operation else 'سجل قديم'}", "effects": effects, "blocked": reason}


@router.delete("/api/maintenance/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_maintenance_record_delete(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    """حذف سجل صيانة واحد عبر API مع الحفاظ على البيانات المرتبطة.

    يُرجع استجابة 204 بلا محتوى ولا رأس Content-Type، لتجنب اعتراض
    أدوات الواجهة العامة (مثل edit-manager.js) التي تحاول تحليل JSON من استجابات فارغة.
    """
    from fastapi import Response
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود.")
    reason = maintenance_record_delete_reason(rec)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    db.delete(rec)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف سجل الصيانة.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/maintenance/records/bulk-delete", response_model=dict)
def api_maintenance_records_bulk_delete(
    payload: MaintenanceRecordBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    deleted_ids = []
    rejected = []
    try:
        for record_id in payload.record_ids:
            record = db.get(MaintenanceRecord, record_id)
            if record is None:
                rejected.append({
                    "record_id": record_id,
                    "record_label": f"سجل #{record_id}",
                    "reason": "سجل الصيانة غير موجود.",
                })
                continue
            reason = maintenance_record_delete_reason(record)
            if reason:
                rejected.append({
                    "record_id": record.id,
                    "record_label": f"{record.maintenance_date} — {record.operation.name if record.operation else 'سجل قديم'}",
                    "reason": reason,
                })
                continue
            db.delete(record)
            deleted_ids.append(record_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لسجلات الصيانة.") from exc
    return {"success": len(deleted_ids), "deleted_ids": deleted_ids, "rejected": rejected}


@router.post("/api/maintenance/bulk-delete", response_model=dict)
def api_bulk_delete_operations(
    payload: MaintenanceOperationBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    """حذف آمن جزئي لعمليات المكتبة مع بيان سبب رفض كل عملية."""
    operation_ids = payload.operation_ids
    rejected = []
    deleted = 0

    try:
        for op_id in operation_ids:
            operation = db.get(MaintenanceOperation, op_id)
            if operation is None:
                rejected.append({"operation_id": op_id, "operation_name": f"# {op_id}", "reason": "العملية غير موجودة"})
                continue

            # Check if operation is linked to any maintenance records
            has_records = db.query(MaintenanceRecord).filter(
                MaintenanceRecord.operation_id == op_id
            ).first() is not None

            if has_records:
                rejected.append({
                    "operation_id": op_id,
                    "operation_name": operation.name,
                    "reason": "لا يمكن حذف العملية لأنها مرتبطة بسجل صيانة. عطّل العملية بدلًا من حذفها."
                })
                continue

            # Check if operation is linked to any plans
            has_plan_links = db.query(MaintenancePlanOperation).filter(
                MaintenancePlanOperation.operation_id == op_id
            ).first() is not None

            if has_plan_links:
                rejected.append({
                    "operation_id": op_id,
                    "operation_name": operation.name,
                    "reason": "لا يمكن حذف العملية لأنها مرتبطة بخطط الصيانة. أزل ارتباطها بالخطة أولًا."
                })
                continue

            db.delete(operation)
            deleted += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لعمليات الصيانة.") from exc

    return {"success": deleted, "rejected": rejected}


@router.get("/maintenance/due", response_class=HTMLResponse)
def maintenance_due_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    unrecorded_only = request.query_params.get("status") == "unrecorded"
    displayed_states = {"بلا سجل"} if unrecorded_only else {"مستحقة الآن", "تقترب"}
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).all()
    model_ids = {eq.equipment_model_id for eq in equipment if eq.equipment_model_id is not None}
    approved_model_ids = {
        model_id for (model_id,) in db.query(MaintenancePlan.equipment_model_id).filter(
            MaintenancePlan.equipment_model_id.in_(model_ids or {-1}),
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        ).distinct().all()
    }
    unapproved_models = sorted({
        eq.equipment_model.name
        for eq in equipment
        if eq.equipment_model_id is not None
        and eq.equipment_model is not None
        and eq.equipment_model_id not in approved_model_ids
    })
    unapproved_model_rows = sorted({
        (eq.equipment_model_id, eq.equipment_model.name)
        for eq in equipment
        if eq.equipment_model_id is not None
        and eq.equipment_model is not None
        and eq.equipment_model_id not in approved_model_ids
    }, key=lambda item: (item[1], item[0]))
    readings = latest_readings(db)
    records = latest_records(db)
    due_rows = []
    plan_groups = []
    standalone_rows = []
    group_map: dict = {}
    tasks_by_model: dict = {}

    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        model_id = eq.equipment_model_id
        if model_id is not None and model_id not in tasks_by_model:
            tasks_by_model[model_id] = operation_tasks_for_model(db, model_id)
        # كل مهمة تحمل سياقها: عملية خطة بشرط خطتها، أو عملية مستقلة بشرط طرازها.
        for task in tasks_by_model.get(model_id, []):
            operation = task.operation
            rec = records.get((eq.id, *operation_reference(operation)))
            state, css, remaining, meta = status_for(operation, eq, rec, current_value, condition=task.condition)
            if state not in displayed_states:
                continue
            row = {
                "equipment": eq,
                "operation": operation,
                "record": rec,
                "current": current_value,
                "unit": measurement_unit(eq),
                "remaining": remaining,
                "remaining_days": meta.get("remaining_days"),
                "state": state,
                "css": css,
                "priority": priority_for(state, remaining, meta),
                "contradiction": contradiction_for(eq, rec, current_value, db),
            }
            due_rows.append(row)
            if task.plan is not None:
                group = group_map.get(task.plan.id)
                if group is None:
                    group = {"plan": task.plan, "rows": []}
                    group_map[task.plan.id] = group
                    plan_groups.append(group)
                group["rows"].append(row)
            else:
                standalone_rows.append(row)

    due_rows.sort(key=lambda r: (
        r["priority"],
        r["remaining"] if r["remaining"] is not None else Decimal("999999999"),
        r["remaining_days"] if r["remaining_days"] is not None else 999999999,
        r["equipment"].registration_number or r["equipment"].asset_code or "",
    ))

    plan_groups.sort(key=lambda group: (group["plan"].name, group["plan"].id))
    return templates.TemplateResponse(
        request=request, name="maintenance_due.html", context={
            "request": request,
            "user": current_user,
            "rows": due_rows,
            "plan_groups": plan_groups,
            "standalone_rows": standalone_rows,
            "unapproved_models": unapproved_models,
            "unapproved_model_rows": unapproved_model_rows,
            "unrecorded_only": unrecorded_only,
        },
    )

# JSON API for the operation-first maintenance library.
@router.get("/api/maintenance/operation-groups", response_model=list[MaintenanceOperationGroupOut])
def api_operation_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(MaintenanceOperationGroup).order_by(MaintenanceOperationGroup.sort_order, MaintenanceOperationGroup.name, MaintenanceOperationGroup.id).all()

@router.post("/api/maintenance/operation-groups", response_model=MaintenanceOperationGroupOut, status_code=status.HTTP_201_CREATED)
def api_operation_group_create(payload: MaintenanceOperationGroupCreate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    group = MaintenanceOperationGroup(**payload.model_dump()); db.add(group)
    try: db.commit(); db.refresh(group)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="اسم مجموعة شروط الصيانة مستخدم مسبقًا.") from exc
    return group

@router.put("/api/maintenance/operation-groups/{group_id}", response_model=MaintenanceOperationGroupOut)
def api_operation_group_update(group_id: int, payload: MaintenanceOperationGroupUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None: raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    for key, value in payload.model_dump().items(): setattr(group, key, value)
    try: db.commit(); db.refresh(group)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="اسم مجموعة شروط الصيانة مستخدم مسبقًا.") from exc
    return group

@router.get("/api/maintenance/operation-groups/{group_id}/delete-impact")
def api_operation_group_delete_impact(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    general_count = db.query(MaintenanceOperation.id).filter(MaintenanceOperation.group_id == group_id).count()
    model_count = db.query(MaintenanceModelOperation.id).filter(MaintenanceModelOperation.group_id == group_id).count()
    return {"label": group.name, "effects": [{"label": "العمليات العامة التي ستبقى بلا مجموعة", "count": general_count, "kind": "unlink"}, {"label": "عمليات الطراز التي ستبقى بلا مجموعة", "count": model_count, "kind": "unlink"}]}

@router.get("/api/maintenance/equipment/models")

def api_equipment_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):

    """Return all equipment models for operation-model association."""

    models = db.query(EquipmentModel).options(

        joinedload(EquipmentModel.equipment_type),

        joinedload(EquipmentModel.brand)

    ).order_by(EquipmentModel.name).all()

    return [{"id": m.id, "name": m.name, "type": m.equipment_type.name if m.equipment_type else "", "brand": m.brand.name if m.brand else ""} for m in models]



@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    db.delete(group)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف مجموعة شروط الصيانة.") from exc
    return None

@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مرتبطة بخطة صيانة. عطّلها بدلًا من حذفها.")
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مستخدمة في سجل الصيانة. عطّلها بدلًا من حذفها.")
    db.delete(operation)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف عملية الصيانة.") from exc
    return None

@router.get("/api/maintenance/operations/{operation_id}/delete-impact")
def api_operation_delete_impact(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    plan_count = db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).count()
    record_count = db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).count()
    blocked = "لا يمكن حذف العملية لارتباطها بخطط أو سجلات تنفيذ؛ عطّلها أو أزل ارتباطاتها أولًا." if plan_count or record_count else None
    return {"label": operation.name, "effects": [
        {"label": "روابط العملية بالطرازات التي ستحذف معها", "count": len(operation.equipment_models)},
        {"label": "روابط الخطط التي تمنع الحذف", "count": plan_count, "kind": "blocked"},
        {"label": "سجلات التنفيذ التي تمنع الحذف", "count": record_count, "kind": "blocked"},
    ], "blocked": blocked}


@router.get("/api/maintenance/operations", response_model=list[MaintenanceOperationOut])
def api_operations(
    equipment_model_id: int | None = Query(default=None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    query = db.query(MaintenanceOperation)
    if equipment_model_id is not None and db.get(EquipmentModel, equipment_model_id) is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    operations = query.order_by(MaintenanceOperation.name, MaintenanceOperation.id).all()
    return operations_payload(db, operations)


@router.get("/api/maintenance/model-operations", response_model=list[MaintenanceModelOperationOut])
def api_model_operations(
    equipment_model_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.get(EquipmentModel, equipment_model_id) is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    return db.query(MaintenanceModelOperation).filter(
        MaintenanceModelOperation.equipment_model_id == equipment_model_id,
    ).order_by(MaintenanceModelOperation.name, MaintenanceModelOperation.id).all()


@router.post("/api/maintenance/model-operations", response_model=MaintenanceModelOperationOut, status_code=status.HTTP_201_CREATED)
def api_model_operation_create(
    payload: MaintenanceModelOperationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    if db.get(EquipmentModel, payload.equipment_model_id) is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    if payload.group_id is not None and db.get(MaintenanceOperationGroup, payload.group_id) is None:
        raise HTTPException(status_code=404, detail="مجموعة العمليات غير موجودة.")
    operation = MaintenanceModelOperation(**payload.model_dump())
    db.add(operation)
    try:
        db.commit()
        db.refresh(operation)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إنشاء عملية الطراز.") from exc
    return operation


@router.put("/api/maintenance/model-operations/{operation_id}", response_model=MaintenanceModelOperationOut)
def api_model_operation_update(
    operation_id: int,
    payload: MaintenanceModelOperationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    operation = db.get(MaintenanceModelOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الطراز غير موجودة.")
    if payload.group_id is not None and db.get(MaintenanceOperationGroup, payload.group_id) is None:
        raise HTTPException(status_code=404, detail="مجموعة العمليات غير موجودة.")
    data = payload.model_dump()
    linked_plans = db.query(MaintenancePlan).join(
        MaintenancePlanOperation, MaintenancePlanOperation.plan_id == MaintenancePlan.id,
    ).filter(MaintenancePlanOperation.model_operation_id == operation.id).all()
    for plan in linked_plans:
        mismatch = _operation_condition_mismatch(plan, payload, db)
        if mismatch:
            raise HTTPException(status_code=409, detail=f"لا يمكن تعديل شرط العملية لارتباطها بالخطة «{plan.name}»: {mismatch}")
    for key, value in data.items():
        setattr(operation, key, value)
    for plan in linked_plans:
        plan.is_approved = False
    try:
        db.commit()
        db.refresh(operation)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تعديل عملية الطراز.") from exc
    return operation


@router.get("/api/maintenance/model-operations/{operation_id}/delete-impact")
def api_model_operation_delete_impact(
    operation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    operation = db.get(MaintenanceModelOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الطراز غير موجودة.")
    plans = db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.model_operation_id == operation_id).count()
    records = db.query(MaintenanceRecord.id).filter(MaintenanceRecord.model_operation_id == operation_id).count()
    return {
        "label": f"{operation.name} — {operation.equipment_model.name}",
        "effects": [
            {"label": "ارتباطات الخطط التي تمنع الحذف", "count": plans, "kind": "blocked"},
            {"label": "سجلات التنفيذ التي تمنع الحذف", "count": records, "kind": "blocked"},
        ],
        "blocked": "لا يمكن حذف العملية لارتباطها بخطة أو سجل تنفيذ؛ عطّلها بدلًا من حذفها." if plans or records else None,
    }


@router.delete("/api/maintenance/model-operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_model_operation_delete(
    operation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    operation = db.get(MaintenanceModelOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الطراز غير موجودة.")
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.model_operation_id == operation_id).first():
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لارتباطها بخطة صيانة. عطّلها بدلًا من حذفها.")
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.model_operation_id == operation_id).first():
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لارتباطها بسجل صيانة. عطّلها بدلًا من حذفها.")
    db.delete(operation)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف عملية الطراز.") from exc
    return None


@router.post("/api/maintenance/model-operations/bulk-delete", response_model=dict)
def api_model_operations_bulk_delete(
    payload: MaintenanceOperationBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    deleted = 0
    rejected = []
    for operation_id in payload.operation_ids:
        operation = db.get(MaintenanceModelOperation, operation_id)
        if operation is None:
            rejected.append({"operation_id": operation_id, "operation_name": f"#{operation_id}", "reason": "عملية الطراز غير موجودة."})
            continue
        if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.model_operation_id == operation_id).first():
            rejected.append({"operation_id": operation_id, "operation_name": operation.name, "reason": "العملية مرتبطة بخطة؛ عطّلها بدلًا من حذفها."})
            continue
        if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.model_operation_id == operation_id).first():
            rejected.append({"operation_id": operation_id, "operation_name": operation.name, "reason": "العملية مستخدمة في سجل صيانة؛ عطّلها بدلًا من حذفها."})
            continue
        db.delete(operation)
        deleted += 1
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لعمليات الطراز.") from exc
    return {"success": deleted, "rejected": rejected}

@router.post("/api/maintenance/operations", response_model=MaintenanceOperationOut, status_code=status.HTTP_201_CREATED)
def api_operation_create(payload: MaintenanceOperationCreate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    data = payload.model_dump()
    if data.get("group_id") is not None and db.get(MaintenanceOperationGroup, data["group_id"]) is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")

    equipment_model_conditions = data.pop("equipment_model_conditions", [])
    # Legacy interval fields on the operation are not used; they remain None.
    # The authoritative conditions are stored per-model in maintenance_operation_models.
    # Warning fields are unified at operation level - KEEP them.
    for field in ("interval_km", "interval_hours", "interval_days"):
        data.pop(field, None)

    operation = MaintenanceOperation(**data)
    db.add(operation)
    db.flush()  # Get the operation ID

    if equipment_model_conditions:
        _sync_operation_model_conditions(db, operation, equipment_model_conditions)

    try:
        db.commit()
        db.refresh(operation)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إنشاء عملية الصيانة.") from exc
    return operations_payload(db, [operation])[0]

@router.put("/api/maintenance/operations/{operation_id}", response_model=MaintenanceOperationOut)
def api_operation_update(operation_id: int, payload: MaintenanceOperationUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None: raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    data = payload.model_dump()
    if data.get("group_id") is not None and db.get(MaintenanceOperationGroup, data["group_id"]) is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")

    # Handle equipment_model_conditions separately
    equipment_model_conditions = data.pop("equipment_model_conditions", None)

    # Legacy interval fields on the operation are not used; they remain unchanged.
    # The authoritative conditions are stored per-model in maintenance_operation_models.
    # Warning fields are unified at operation level - KEEP them.
    for field in ("interval_km", "interval_hours", "interval_days"):
        data.pop(field, None)

    for key, value in data.items(): setattr(operation, key, value)

    # Update equipment_model_conditions if provided, and validate against plans
    if equipment_model_conditions is not None:
        # Sync the model conditions (this will update the maintenance_operation_models table)
        _sync_operation_model_conditions(db, operation, equipment_model_conditions)

        # Check if any affected plan's model is no longer in the operation's models
        affected_plans = db.query(MaintenancePlan).join(
            MaintenancePlanOperation, MaintenancePlanOperation.plan_id == MaintenancePlan.id
        ).filter(MaintenancePlanOperation.operation_id == operation.id).all()
        
        # Get the updated model IDs from the synced conditions
        current_model_ids = {m.id for m in operation.equipment_models}
        
        model_errors = []
        for plan in affected_plans:
            if plan.equipment_model_id not in current_model_ids:
                model_errors.append(f"خطة '{plan.name}' (ID: {plan.id}) تتطلب طراز العتاد {plan.equipment_model_id} الذي لم يعد مرتبطًا بالعملية")
        
        if model_errors:
            # We can't easily rollback the _sync_operation_model_conditions, so we raise an error
            # The transaction will be rolled back by the exception handler
            raise HTTPException(
                status_code=409,
                detail="تعذر تعديل العملية: تغيير الطرازات المرتبطة يتعارض مع الخطط التالية:\n" + "\n".join(model_errors)
            )

    # Plans that contain this operation no longer depend on its per-model
    # condition: each plan operation is governed by the plan's condition. Editing
    # the operation therefore neither rejects nor redefines any plan; plans that
    # contain it are only flagged for a fresh review.
    affected_plans = db.query(MaintenancePlan).join(
        MaintenancePlanOperation, MaintenancePlanOperation.plan_id == MaintenancePlan.id
    ).filter(MaintenancePlanOperation.operation_id == operation.id).all()
    for plan in affected_plans:
        plan.is_approved = False

    try: db.commit(); db.refresh(operation)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر تعديل عملية الصيانة.") from exc
    return operations_payload(db, [operation])[0]


# Operation-Model relationship endpoints
@router.get("/api/maintenance/operations/{operation_id}/models", response_model=list[dict])
def api_operation_models(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    return [{"id": m.id, "name": m.name} for m in operation.equipment_models]


@router.post("/api/maintenance/operations/{operation_id}/models", status_code=status.HTTP_201_CREATED)
def api_operation_add_model(operation_id: int, equipment_model_id: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    model = db.get(EquipmentModel, equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    if model in operation.equipment_models:
        raise HTTPException(status_code=409, detail="العملية مرتبطة بهذا الطراز مسبقًا.")
    operation.equipment_models.append(model)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إضافة الطراز للعملية.") from exc
    return {"operation_id": operation.id, "equipment_model_id": model.id, "name": model.name}


@router.delete("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_remove_model(operation_id: int, equipment_model_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    model = db.get(EquipmentModel, equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    if model not in operation.equipment_models:
        raise HTTPException(status_code=404, detail="العملية غير مرتبطة بهذا الطراز.")
    affected_plans = db.query(MaintenancePlan).join(
        MaintenancePlanOperation,
        MaintenancePlanOperation.plan_id == MaintenancePlan.id,
    ).filter(
        MaintenancePlan.equipment_model_id == model.id,
        MaintenancePlanOperation.operation_id == operation.id,
        MaintenancePlan.is_approved.is_(True),
    ).all()
    for plan in affected_plans:
        plan.is_approved = False
    operation.equipment_models.remove(model)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إزالة الطراز من العملية.") from exc
    return None


def _save_operation_model_condition(
    operation_id: int,
    equipment_model_id: int,
    payload: MaintenanceOperationModelConditionSave,
    db: Session,
    *,
    update: bool,
):
    """Save one model's independent condition without editing the library operation or plans."""
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if not operation.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن ربط عملية صيانة غير مفعلة بطراز.")
    model = db.get(EquipmentModel, equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    relation = maintenance_operation_models
    existing = db.execute(
        relation.select().where(
            relation.c.operation_id == operation_id,
            relation.c.equipment_model_id == equipment_model_id,
        )
    ).first()
    if update and (existing is None or existing.condition_source != "model"):
        raise HTTPException(status_code=404, detail="لا يوجد شرط مستقل محفوظ لهذه العملية والطراز.")
    if not update and existing is not None and existing.condition_source == "model":
        raise HTTPException(status_code=409, detail="للعملية شرط مستقل محفوظ لهذا الطراز مسبقًا.")

    values = {
        "condition_source": "model",
        "interval_km": payload.interval_km,
        "interval_hours": payload.interval_hours,
        "interval_days": payload.interval_days,
    }
    try:
        if existing is None:
            db.execute(relation.insert().values(
                operation_id=operation_id,
                equipment_model_id=equipment_model_id,
                is_active=True,
                **values,
            ))
        else:
            db.execute(relation.update().where(
                relation.c.operation_id == operation_id,
                relation.c.equipment_model_id == equipment_model_id,
            ).values(**values))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حفظ شرط العملية المستقلة للطراز.") from exc
    return {"operation_id": operation_id, "model_id": equipment_model_id, **values}


@router.post("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}/condition", status_code=status.HTTP_201_CREATED)
def api_operation_model_condition_create(
    operation_id: int,
    equipment_model_id: int,
    payload: MaintenanceOperationModelConditionSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    return _save_operation_model_condition(operation_id, equipment_model_id, payload, db, update=False)


@router.patch("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}/condition")
def api_operation_model_condition_update(
    operation_id: int,
    equipment_model_id: int,
    payload: MaintenanceOperationModelConditionSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    return _save_operation_model_condition(operation_id, equipment_model_id, payload, db, update=True)


@router.get("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}/remove-impact")
def api_operation_remove_model_impact(operation_id: int, equipment_model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    model = db.get(EquipmentModel, equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    if model not in operation.equipment_models:
        raise HTTPException(status_code=404, detail="العملية غير مرتبطة بهذا الطراز.")
    approved_plans = db.query(MaintenancePlan.id).join(
        MaintenancePlanOperation,
        MaintenancePlanOperation.plan_id == MaintenancePlan.id,
    ).filter(
        MaintenancePlan.equipment_model_id == model.id,
        MaintenancePlanOperation.operation_id == operation.id,
        MaintenancePlan.is_approved.is_(True),
    ).count()
    return {
        "label": f"{operation.name} — {model.name}",
        "effects": [
            {"label": "ارتباط العملية بالطراز الذي سيزال", "count": 1, "kind": "unlink"},
            {"label": "خطط معتمدة ستحتاج إلى اعتماد جديد", "count": approved_plans, "kind": "recalculate"},
        ],
    }

@router.get("/api/maintenance/plans", response_model=list[MaintenancePlanOut])
def api_plans(equipment_model_id: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(MaintenancePlan)
    if equipment_model_id is not None: query = query.filter(MaintenancePlan.equipment_model_id == equipment_model_id)
    return query.order_by(MaintenancePlan.name, MaintenancePlan.id).all()

@router.post("/api/maintenance/plans", response_model=MaintenancePlanOut, status_code=status.HTTP_201_CREATED)
def api_plan_create(payload: MaintenancePlanCreate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    if db.get(EquipmentModel, payload.equipment_model_id) is None: raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    plan = MaintenancePlan(**payload.model_dump()); db.add(plan)
    try: db.commit(); db.refresh(plan)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر إنشاء خطة الصيانة.") from exc
    return plan

@router.post("/api/maintenance/plans/bulk-delete", response_model=dict)
def api_plans_bulk_delete(payload: MaintenancePlanBulkDelete, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    """حذف الخطط الآمنة، مع رفض الخطط التي تحفظ سياق تنفيذ تاريخي.

    كل رفض يعيد معرّف الخطة وسبب منع حذفها. لا يُحذف تعريف عملية من المكتبة.
    """
    deleted = 0
    rejected: list[dict] = []
    try:
        for plan_id in payload.plan_ids:
            plan = db.get(MaintenancePlan, plan_id)
            if plan is None:
                rejected.append({"plan_id": plan_id, "plan_name": f"# {plan_id}", "reason": "خطة الصيانة غير موجودة"})
                continue
            try:
                _delete_plan(db, plan)
            except ValueError as exc:
                rejected.append({"plan_id": plan.id, "plan_name": plan.name, "reason": str(exc)})
            else:
                deleted += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لخطط الصيانة.") from exc
    return {"success": deleted, "rejected": rejected}

@router.put("/api/maintenance/plans/{plan_id}", response_model=MaintenancePlanOut)
def api_plan_update(plan_id: int, payload: MaintenancePlanUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if db.get(EquipmentModel, payload.equipment_model_id) is None: raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")

    # Capture original values for potential rollback
    original_interval_km = plan.interval_km
    original_interval_hours = plan.interval_hours
    original_interval_days = plan.interval_days

    for key, value in payload.model_dump().items(): setattr(plan, key, value)

    # Any plan edit requires explicit re-approval before it drives follow-ups.
    plan.is_approved = False
    try: db.commit(); db.refresh(plan)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر تعديل خطة الصيانة.") from exc
    return plan

@router.delete("/api/maintenance/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_plan_delete(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    """حذف خطة صيانة لا ترتبط بتنفيذ تاريخي فقط."""
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    try:
        _delete_plan(db, plan)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف خطة الصيانة.") from exc
    return None

@router.get("/api/maintenance/plans/{plan_id}/delete-impact")
def api_plan_delete_impact(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    record_count = db.query(MaintenanceRecord.id).filter(MaintenanceRecord.plan_id == plan.id).count()
    operation_count = db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.plan_id == plan.id).count()
    return {"label": plan.name, "effects": [
        {"label": "روابط العمليات التي ستزال من الخطة", "count": operation_count},
        {"label": "سجلات التنفيذ التي تمنع حذف الخطة", "count": record_count, "kind": "blocked"},
    ], "blocked": "لا يمكن حذف الخطة لارتباطها بسجلات تنفيذ تاريخية." if record_count else None}

@router.post("/api/maintenance/plans/{plan_id}/approve", response_model=MaintenancePlanOut)
def api_plan_approve(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن اعتماد خطة صيانة متوقفة.")
    links = db.query(MaintenancePlanOperation).options(
        joinedload(MaintenancePlanOperation.operation),
        joinedload(MaintenancePlanOperation.model_operation),
    ).filter(MaintenancePlanOperation.plan_id == plan.id).all()
    for link in links:
        if link.model_operation_id is not None:
            operation = link.model_operation
            if operation is None or operation.equipment_model_id != plan.equipment_model_id:
                raise HTTPException(status_code=409, detail="تحتوي الخطة على عملية خاصة بطراز آخر أو مفقودة؛ لا يمكن اعتمادها.")
            mismatch = _operation_condition_mismatch(plan, operation, db)
            if mismatch:
                raise HTTPException(status_code=409, detail=f"شرط العملية «{operation.name}» لا يوافق شرط الخطة: {mismatch}")
    operation_count = sum(
        1 for link in links
        if (link.operation and link.operation.is_active)
        or (link.model_operation and link.model_operation.is_active)
    )
    if operation_count == 0:
        raise HTTPException(status_code=409, detail="أضف عملية صيانة مفعلة واحدة على الأقل قبل اعتماد الخطة.")
    plan.is_approved = True
    try:
        db.commit()
        db.refresh(plan)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر اعتماد خطة الصيانة.") from exc
    return plan


@router.get("/api/maintenance/plans/{plan_id}/operations", response_model=list[MaintenancePlanOperationOut])
def api_plan_operations(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    links = db.query(MaintenancePlanOperation).options(
        joinedload(MaintenancePlanOperation.operation),
        joinedload(MaintenancePlanOperation.model_operation),
    ).filter(MaintenancePlanOperation.plan_id == plan_id).order_by(
        MaintenancePlanOperation.sort_order, MaintenancePlanOperation.id,
    ).all()
    return [_plan_operation_payload(link) for link in links]


@router.post("/api/maintenance/plans/{plan_id}/operations", response_model=MaintenancePlanOperationOut, status_code=status.HTTP_201_CREATED)
def api_plan_operation_add(plan_id: int, payload: MaintenancePlanOperationCreate, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(Role.FLEET_MANAGER))):
    if payload.plan_id != plan_id:
        raise HTTPException(status_code=400, detail="رقم الخطة في الطلب لا يطابق المسار.")
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن إضافة عملية إلى خطة صيانة غير مفعلة.")
    source = "model" if payload.model_operation_id is not None else "general"
    operation_id = payload.model_operation_id if source == "model" else payload.operation_id
    operation = _operation_from_source(db, source=source, operation_id=operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if not operation.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن إضافة عملية صيانة غير مفعلة إلى الخطة.")

    # Check if operation is linked to the plan's equipment model
    model = db.get(EquipmentModel, plan.equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد للخطة غير موجود.")
    if source == "model":
        if operation.equipment_model_id != model.id:
            raise HTTPException(status_code=409, detail="هذه العملية الخاصة لا تخص طراز الخطة المحدد.")
        mismatch = _operation_condition_mismatch(plan, operation, db)
        if mismatch:
            raise HTTPException(status_code=409, detail=f"لا يمكن إضافة العملية «{operation.name}»: {mismatch}")
    elif model not in operation.equipment_models:
        operation.equipment_models.append(model)

    link = MaintenancePlanOperation(**payload.model_dump())
    db.add(link)
    plan.is_approved = False
    try:
        db.commit()
        db.refresh(link)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="العملية مرتبطة بهذه الخطة مسبقًا أو أن البيانات غير صالحة.") from exc
    return _plan_operation_payload(link)


@router.post("/api/maintenance/plans/{plan_id}/operations/bulk", status_code=status.HTTP_201_CREATED)
def api_plan_operations_add_bulk(
    plan_id: int,
    payload: MaintenancePlanOperationsBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    """Add compatible selections and report each rejected operation separately."""
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن إضافة عمليات إلى خطة صيانة غير مفعلة.")
    model = db.get(EquipmentModel, plan.equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد للخطة غير موجود.")

    links = []
    rejected = []
    requested = [("general", item_id) for item_id in payload.operation_ids]
    requested.extend(("model", item_id) for item_id in payload.model_operation_ids)
    try:
        for source, operation_id in requested:
            operation = _operation_from_source(db, source=source, operation_id=operation_id)
            if operation is None:
                rejected.append({"source": source, "operation_id": operation_id, "operation_name": f"#{operation_id}", "reason": "عملية الصيانة غير موجودة."})
                continue
            if not operation.is_active:
                rejected.append({"source": source, "operation_id": operation_id, "operation_name": operation.name, "reason": "العملية غير مفعلة."})
                continue
            if source == "model" and operation.equipment_model_id != plan.equipment_model_id:
                rejected.append({"source": source, "operation_id": operation_id, "operation_name": operation.name, "reason": "العملية الخاصة لا تخص طراز الخطة."})
                continue
            if source == "model":
                mismatch = _operation_condition_mismatch(plan, operation, db)
                if mismatch:
                    rejected.append({"source": source, "operation_id": operation_id, "operation_name": operation.name, "reason": mismatch})
                    continue
            filter_by_ref = _plan_link_filter(source, operation_id)
            if db.query(MaintenancePlanOperation.id).filter(
                MaintenancePlanOperation.plan_id == plan_id, filter_by_ref,
            ).first():
                rejected.append({"source": source, "operation_id": operation_id, "operation_name": operation.name, "reason": "العملية مرتبطة بهذه الخطة مسبقًا."})
                continue
            if source == "general" and model not in operation.equipment_models:
                operation.equipment_models.append(model)
            link = MaintenancePlanOperation(
                plan_id=plan_id,
                operation_id=operation_id if source == "general" else None,
                model_operation_id=operation_id if source == "model" else None,
                sort_order=len(links),
            )
            db.add(link)
            links.append(link)
        if links:
            plan.is_approved = False
        db.commit()
        for link in links:
            db.refresh(link)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إضافة العمليات المحددة؛ لم تُحفظ أي عملية.") from exc
    return {"added": [_plan_operation_payload(link) for link in links], "success": len(links), "rejected": rejected}

@router.delete("/api/maintenance/plans/{plan_id}/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_plan_operation_remove(
    plan_id: int,
    operation_id: int,
    source: str = Query(default="general", pattern="^(general|model)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    link = db.query(MaintenancePlanOperation).filter(
        MaintenancePlanOperation.plan_id == plan_id,
        _plan_link_filter(source, operation_id),
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="العملية غير مرتبطة بهذه الخطة.")
    db.delete(link)
    plan.is_approved = False
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إزالة العملية من الخطة.") from exc
    return None


@router.get("/api/maintenance/plans/{plan_id}/operations/{operation_id}/remove-impact")
def api_plan_operation_remove_impact(
    plan_id: int,
    operation_id: int,
    source: str = Query(default="general", pattern="^(general|model)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    link = db.query(MaintenancePlanOperation).filter(
        MaintenancePlanOperation.plan_id == plan_id,
        _plan_link_filter(source, operation_id),
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="العملية غير مرتبطة بهذه الخطة.")
    operation = _operation_from_source(db, source=source, operation_id=operation_id)
    return {
        "label": f"{operation.name if operation else 'عملية الصيانة'} — {plan.name}",
        "effects": [
            {"label": "ارتباط العملية بالخطة الذي سيزال", "count": 1, "kind": "unlink"},
            {"label": "اعتماد الخطة سيُلغى ويلزم اعتماده مجددًا", "count": int(bool(plan.is_approved)), "kind": "recalculate"},
        ],
    }


@router.get("/api/maintenance/execution", response_model=list[MaintenanceRecordOut])
def api_execution_records(
    equipment_id: int | None = None,
    operation_id: int | None = None,
    model_operation_id: int | None = None,
    plan_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(MaintenanceRecord)
    if equipment_id is not None: query = query.filter(MaintenanceRecord.equipment_id == equipment_id)
    if operation_id is not None: query = query.filter(MaintenanceRecord.operation_id == operation_id)
    if model_operation_id is not None: query = query.filter(MaintenanceRecord.model_operation_id == model_operation_id)
    if plan_id is not None: query = query.filter(MaintenanceRecord.plan_id == plan_id)
    return query.order_by(MaintenanceRecord.maintenance_date.desc(), MaintenanceRecord.id.desc()).all()


@router.post("/api/maintenance/execution", response_model=MaintenanceRecordOut, status_code=status.HTTP_201_CREATED)
def api_execution_create(
    payload: MaintenanceRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == payload.equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="العتاد المحدد غير موجود.")
    if payload.maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")

    source = "model" if payload.model_operation_id is not None else "general"
    operation_id = payload.model_operation_id if source == "model" else payload.operation_id
    operation = _operation_from_source(db, source=source, operation_id=operation_id)
    plan = db.get(MaintenancePlan, payload.plan_id) if payload.plan_id is not None else None

    if operation is None:
        raise HTTPException(status_code=400, detail="يجب تحديد عملية الصيانة.")
    if operation is not None and not operation.is_active:
        raise HTTPException(status_code=409, detail="عملية الصيانة غير مفعلة.")
    if plan is not None:
        if not plan.is_active:
            raise HTTPException(status_code=409, detail="خطة الصيانة غير مفعلة.")
        if not plan.is_approved:
            raise HTTPException(status_code=409, detail="لا يمكن ربط سجل تنفيذ بخطة غير معتمدة.")
        if plan.equipment_model_id != equipment.equipment_model_id:
            raise HTTPException(status_code=409, detail="خطة الصيانة لا تخص طراز العتاد المحدد.")

    # Validate operation applicability to equipment using shared function
    validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
    if validation_error:
        raise HTTPException(status_code=409, detail=validation_error)

    # If a plan is specified, verify the operation belongs to that plan
    if plan is not None:
        linked = db.query(MaintenancePlanOperation.id).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            _plan_link_filter(source, operation.id),
        ).first()
        if linked is None:
            raise HTTPException(status_code=409, detail="العملية المختارة غير مرتبطة بالخطة المحددة.")

    # Validate the technician reference when supplied.
    technician = None
    if payload.technician_id is not None:
        technician = db.get(Technician, payload.technician_id)
        if technician is None or not technician.is_active:
            raise HTTPException(status_code=409, detail="الفني المحدد غير موجود أو غير نشط.")

    # The meter requirement follows the governing condition: a plan record uses
    # the plan's condition, a standalone record uses the operation's model condition.
    from app.modules.maintenance.services import operation_condition_for_model, meter_required_for_condition
    if plan is not None:
        model_condition = plan_condition(plan)
    else:
        if isinstance(operation, MaintenanceModelOperation):
            model_condition = ModelCondition(
                condition_source="model",
                equipment_model_id=operation.equipment_model_id,
                interval_km=operation.interval_km,
                interval_hours=operation.interval_hours,
                interval_days=operation.interval_days,
            )
        else:
            model_condition = operation_condition_for_model(db, operation.id, equipment.equipment_model_id)
    unit = measurement_unit(equipment)
    if payload.meter_value is not None and payload.meter_value < 0:
        raise HTTPException(status_code=400, detail="لا يمكن أن تكون قراءة العداد سالبة.")
    if meter_required_for_condition(model_condition, unit) and payload.meter_value is None:
        raise HTTPException(status_code=400, detail="يجب إدخال قراءة العداد لهذه العملية.")

    chronology = chronology_error(db, payload.equipment_id, payload.maintenance_date, payload.meter_value)
    if chronology:
        raise HTTPException(status_code=409, detail=chronology)

    record = MaintenanceRecord(
        equipment_id=payload.equipment_id,
        operation_id=operation.id if source == "general" else None,
        model_operation_id=operation.id if source == "model" else None,
        plan_id=payload.plan_id,
        maintenance_date=payload.maintenance_date,
        reported_date=payload.reported_date or payload.maintenance_date,
        meter_value=payload.meter_value,
        work_order=payload.work_order,
        workshop=payload.workshop,
        technician_id=technician.id if technician is not None else None,
        status=payload.status or "completed",
        is_scheduled=payload.is_scheduled,
        description=payload.description,
        note=payload.note,
        created_by_id=current_user.id if current_user else None,
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تسجيل تنفيذ الصيانة؛ تحقق من عدم تكرار السجل والبيانات المرتبطة.") from exc
    return record


@router.get("/api/maintenance/plan-status")
def api_plan_status(
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="العتاد المحدد غير موجود.")
    readings = latest_readings(db)
    current_value = current_meter_value(equipment, readings.get(equipment.id))
    latest_plans = latest_plan_records(db)
    rows = []
    for plan in effective_plans_for_equipment(db, equipment):
        record = latest_plans.get((equipment.id, plan.id))
        state, css, remaining, meta = plan_status_for(plan, equipment, record, current_value)
        rows.append({
            "plan_id": plan.id,
            "name": plan.name,
            "equipment_model_id": plan.equipment_model_id,
            "interval_km": plan.interval_km,
            "interval_hours": plan.interval_hours,
            "interval_days": plan.interval_days,
            "state": state,
            "css": css,
            "remaining": remaining,
            "remaining_days": meta.get("remaining_days"),
            "next_meter": meta.get("next_meter"),
            "next_date": meta.get("next_date"),
            "last_execution_date": record.maintenance_date if record else None,
            "last_execution_meter": record.meter_value if record else None,
        })
    return rows


@router.post("/api/maintenance/plan-execution", response_model=list[MaintenanceRecordOut], status_code=status.HTTP_201_CREATED)
def api_plan_execution_create(
    payload: MaintenancePlanExecutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == payload.equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="العتاد المحدد غير موجود.")
    plan = db.get(MaintenancePlan, payload.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="خطة الصيانة غير مفعلة.")
    if not plan.is_approved:
        raise HTTPException(status_code=409, detail="لا يمكن تنفيذ خطة غير معتمدة.")
    if plan.equipment_model_id != equipment.equipment_model_id:
        raise HTTPException(status_code=409, detail="خطة الصيانة لا تخص طراز العتاد المحدد.")
    if payload.maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")

    selected_refs = [*(('general', operation_id) for operation_id in payload.operation_ids), *(('model', operation_id) for operation_id in payload.model_operation_ids)]
    links = db.query(MaintenancePlanOperation).options(
        joinedload(MaintenancePlanOperation.operation),
        joinedload(MaintenancePlanOperation.model_operation),
    ).filter(MaintenancePlanOperation.plan_id == plan.id).all()
    active_links = {}
    for link in links:
        operation = link.operation or link.model_operation
        if operation is not None and operation.is_active:
            source = "model" if link.model_operation_id is not None else "general"
            operation_id = link.model_operation_id if source == "model" else link.operation_id
            active_links[(source, operation_id)] = (link, operation)
    invalid_refs = [ref for ref in selected_refs if ref not in active_links]
    if invalid_refs:
        raise HTTPException(status_code=409, detail="توجد عملية محددة ليست ضمن العمليات المفعلة لهذه الخطة.")

    # Verify all selected operations are linked to the equipment's model
    for operation_ref in selected_refs:
        _, operation = active_links[operation_ref]
        validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
        if validation_error:
            raise HTTPException(status_code=409, detail=f"عملية {operation.name}: {validation_error}")

    unit = measurement_unit(equipment)
    if payload.meter_value is not None and payload.meter_value < 0:
        raise HTTPException(status_code=400, detail="لا يمكن أن تكون قراءة العداد سالبة.")
    # كل عمليات الخطة ترث شرط الخطة، فتتطلب قراءة العداد وفق محاور الخطة.
    from app.modules.maintenance.services import meter_required_for_condition
    plan_cond = plan_condition(plan)
    for operation_ref in selected_refs:
        _, operation = active_links[operation_ref]
        if meter_required_for_condition(plan_cond, unit) and payload.meter_value is None:
            raise HTTPException(status_code=400, detail=f"يجب إدخال قراءة العداد للعملية: {operation.name}.")

    chronology = chronology_error(db, payload.equipment_id, payload.maintenance_date, payload.meter_value)
    if chronology:
        raise HTTPException(status_code=409, detail=chronology)

    records = []
    try:
        for source, operation_id in selected_refs:
            _, operation = active_links[(source, operation_id)]
            record = MaintenanceRecord(
                equipment_id=payload.equipment_id,
                operation_id=operation.id if source == "general" else None,
                model_operation_id=operation.id if source == "model" else None,
                plan_id=plan.id,
                maintenance_date=payload.maintenance_date,
                reported_date=payload.reported_date or payload.maintenance_date,
                meter_value=payload.meter_value,
                work_order=payload.work_order,
                workshop=payload.workshop,
                status=payload.status or "completed",
                # تنفيذ الخطة هو صيانة فعلية؛ لا يُسجل كسجل مجدول.
                is_scheduled=False,
                description=payload.description,
                created_by_id=current_user.id if current_user else None,
            )
            db.add(record)
            records.append(record)
        db.commit()
        for record in records:
            db.refresh(record)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تسجيل العمليات المحددة؛ لم يتم حفظ أي عملية من الخطة.") from exc
    return records
