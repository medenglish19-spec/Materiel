"""Source-preserving maintenance catalog extraction and review helpers.

Extracted rows intentionally remain reference data. The existing operational
maintenance engine cannot represent all manufacturer schedules (for example,
first-vs-repeat intervals and driving-condition matrices), so this module never
silently converts a catalog into an approved plan.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.document_import.extraction.extractor import ExtractionError, extract_document
from app.modules.maintenance.models import MaintenanceCatalogImport
from app.modules.equipment_types.models import EquipmentModel

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls"}


def _pdf_fragments(path: Path) -> list[list[tuple[float, float, str]]]:
    """Return positioned PDF text fragments, retaining page coordinates."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ExtractionError("pdf_dependency", "استخراج مواضع PDF يتطلب مكتبة pypdf.") from exc
    reader = PdfReader(str(path), strict=False)
    if reader.is_encrypted:
        if not reader.decrypt(""):
            raise ExtractionError("pdf_encrypted", "ملف PDF محمي بكلمة مرور.")
    result = []
    for page in reader.pages:
        fragments = []
        def visit(text, _cm, tm, _font, _size):
            text = " ".join((text or "").split())
            if text:
                fragments.append((round(float(tm[4]), 1), round(float(tm[5]), 1), text))
        page.extract_text(visitor_text=visit)
        result.append(fragments)
    return result


def _clusters(fragments, predicate, max_gap=11.5):
    points = sorted(((y, text) for x, y, text in fragments if predicate(x, y, text)), reverse=True)
    groups = []
    for y, text in points:
        if groups and groups[-1]["ys"][-1] - y <= max_gap:
            groups[-1]["ys"].append(y)
            groups[-1]["texts"].append(text)
        else:
            groups.append({"ys": [y], "texts": [text]})
    for group in groups:
        group["top"] = max(group["ys"])
        group["bottom"] = min(group["ys"])
        group["text"] = " ".join(group["texts"])
    return groups


def _micra_items(pages: list[list[tuple[float, float, str]]], document_text: str):
    """Coordinate-aware row extraction for the supplied Micra table layout.

    Actions are kept verbatim because the PDF encodes sparse marks as strings;
    interpreting those marks as cadence without a human check would be unsafe.
    """
    items = []
    for page_no in (1, 2):
        if page_no > len(pages):
            continue
        fragments = pages[page_no - 1]
        # The leftmost column contains maintenance item names. Header/footer
        # text is excluded by the vertical bounds of the two printed tables.
        groups = _clusters(
            fragments,
            lambda x, y, text: x < 300 and 105 <= y <= 340 and
                not any(marker in text.lower() for marker in ("note", "maintenance", "perform", "km x", "months", "mile", "whichever comes first")),
        )
        for group in groups:
            y = (group["top"] + group["bottom"]) / 2
            related = [f"x={x:g}: {text}" for x, fy, text in fragments if min(abs(fy - group["top"]), abs(fy - group["bottom"])) <= 6.5 and x >= 300]
            related.sort()
            name = group["text"].strip()
            if not name or not re.search(r"[A-Za-z]", name):
                continue
            name = re.sub(r"\s+", " ", name.replace("★", " ")).strip()
            category = "engine_emissions" if page_no == 1 else "chassis_body"
            cell_text = " | ".join(related)
            marks = re.findall(r"\[?([RIL])\]?", cell_text)
            condition = None
            interval_km = 15000 if len(marks) == 10 else 30000 if len(marks) == 5 else None
            if len(marks) == 1:
                x_match = re.search(r"x=([\d.]+):\s*\[?R\]?", cell_text)
                if x_match:
                    x = float(x_match.group(1))
                    grid_x = [388, 430, 472, 515, 557, 600, 642, 685, 728, 770] if page_no == 1 else [391, 433, 475, 518, 560, 603, 645, 688, 729, 770]
                    grid_km = [15000 * n for n in range(1, 11)]
                    nearest = min(range(len(grid_x)), key=lambda index: abs(grid_x[index] - x))
                    interval_km = grid_km[nearest]
            special_match = re.search(r"NOTE\s*\(3\)", cell_text, re.I)
            if special_match:
                coolant = re.search(r"then every\s*([\d ]+)km.*?/(\d+) months", document_text, re.I | re.S)
                if coolant:
                    interval_km = int(coolant.group(1).replace(" ", ""))
            if interval_km:
                months = interval_km / 1250
                condition = {"interval_km": interval_km, "interval_days": round(months * 365.2425 / 12)}
            # The manufacturer note defines the coolant's repeating condition;
            # the initial 75,000 km replacement remains visible in the source.
            if "engine coolant" in name.lower():
                coolant = re.search(r"then every\s*([\d ]+)km.*?/(\d+) months", document_text, re.I | re.S)
                if coolant:
                    condition = {"interval_km": int(coolant.group(1).replace(" ", "")), "interval_days": round(int(coolant.group(2)) * 365.2425 / 12)}
                    cell_text = (cell_text + " | manufacturer note: first at 75,000 km/60 months, then at repeating interval").strip(" |")
            condition_note = None
            if re.search(r"NOTE\s*\(1\)", cell_text, re.I):
                condition_note = "لا تتطلب العملية دوريًا؛ افحص خلوص الصمامات عند زيادة الضجيج."
            elif re.search(r"NOTE\s*\(4\)", cell_text, re.I):
                condition_note = "مرشح الوقود (داخل الخزان) لا يحتاج إلى صيانة دورية وفق المصدر."
            items.append({
                "schedule_type": "normal",
                "section": category,
                "operation_name": name,
                "source_page": page_no,
                "source_location": {"y": round(y, 1)},
                "action_and_cells_raw": cell_text,
                "interval_grid": [
                    {"km": 15000 * n, "months": 12 * n} for n in range(1, 11)
                ],
                "applicability": "1.2ℓ & 1.5ℓ PETROL; engine-specific notes are retained in the operation text",
                "review_state": "needs_review",
                "corrected_condition": condition,
                "condition_note": condition_note,
                "confidence": "row and regular interval extracted; verify against source" if condition else "operation found; add a numeric condition or reject",
            })
    if len(pages) >= 3:
        fragments = pages[2]
        groups = _clusters(fragments, lambda x, y, text: 180 <= x < 500 and 85 <= y <= 245)
        for group in groups:
            y = (group["top"] + group["bottom"]) / 2
            related = [f"x={x:g}: {text}" for x, fy, text in fragments if min(abs(fy - group["top"]), abs(fy - group["bottom"])) <= 6.5 and (x < 180 or x >= 500)]
            related.sort()
            raw_row = " | ".join(related)
            interval_match = re.search(r"Every\s*([\d ]+)km.*?or\s*(\d+) months", raw_row, re.I)
            severe_condition = None
            if interval_match:
                severe_condition = {
                    "interval_km": int(interval_match.group(1).replace(" ", "")),
                    "interval_days": round(int(interval_match.group(2)) * 365.2425 / 12),
                }
            items.append({
                "schedule_type": "severe_conditions",
                "section": "severe_driving_conditions",
                "operation_name": group["text"].strip(),
                "source_page": 3,
                "source_location": {"y": round(y, 1)},
                "action_conditions_interval_raw": raw_row,
                "conditions_legend_source_page": 3,
                "review_state": "supplemental",
                "suggested_condition": severe_condition,
                "corrected_condition": None,
                "confidence": "table row located; condition markers require review",
            })
        aircon = next(((x, y, text) for x, y, text in fragments if "air-conditioner filter" in text.lower()), None)
        if aircon:
            _, y, text = aircon
            related = [f"x={x:g}: {value}" for x, fy, value in fragments if abs(fy - y) <= 3.8 and (x >= 500 or x < 180)]
            raw_row = " | ".join(sorted(related))
            interval_match = re.search(r"Every\s*([\d ]+)km.*?or\s*(\d+) months", raw_row, re.I)
            severe_condition = None
            if interval_match:
                severe_condition = {
                    "interval_km": int(interval_match.group(1).replace(" ", "")),
                    "interval_days": round(int(interval_match.group(2)) * 365.2425 / 12),
                }
            items.append({
                "schedule_type": "severe_conditions", "section": "severe_driving_conditions",
                "operation_name": "Air-conditioner filter", "source_page": 3,
                "source_location": {"y": round(y, 1)}, "action_conditions_interval_raw": raw_row,
                "conditions_legend_source_page": 3, "review_state": "supplemental",
                "suggested_condition": severe_condition,
                "confidence": "table row located; condition markers require review",
            })
    return items


def parse_catalog(filename: str, data: bytes) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("نوع الملف غير مدعوم. الصيغ المتاحة: PDF وDOCX وXLSX وXLS.")
    with tempfile.TemporaryDirectory(prefix="maintenance-catalog-") as temp_dir:
        tmp_path = Path(temp_dir) / ("source" + ext)
        tmp_path.write_bytes(data)
        document = extract_document(tmp_path)
        text = document.text or ""
        pages = _pdf_fragments(tmp_path) if ext == ".pdf" else []

    title = None
    manufacturer = None
    if "NISSAN MICRA" in text.upper():
        manufacturer, title = "Nissan", "Nissan Micra Periodic Maintenance"
    version_match = re.search(r"(?:revision|version|edition)\s*[:#-]?\s*([\w.-]+)", text, re.I)
    items = _micra_items(pages, text) if manufacturer == "Nissan" and "MICRA" in text.upper() else []
    warnings = []
    if not items:
        rows = []
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                value = " | ".join(str(cell).strip() for cell in row if str(cell).strip())
                if value:
                    rows.append({
                        "schedule_type": "unclassified",
                        "section": table.name or f"table_{table_index}",
                        "operation_name": value[:500],
                        "source_page": table.page,
                        "source_location": {"row": row_index},
                        "review_state": "needs_review",
                        "confidence": "raw table row; classification and intervals require review",
                    })
        if not rows and text.strip():
            page_number = None
            for line in text.splitlines():
                page_match = re.match(r"\s*PAGE\s+(\d+)\s*:?\s*$", line, re.I)
                if page_match:
                    page_number = int(page_match.group(1))
                    continue
                candidate = " ".join(line.split())
                if len(candidate) < 8 or len(candidate) > 500:
                    continue
                if re.search(r"\b(replace|inspect|check|lubricate|adjust|clean|renew|grease|changer|contr[oô]ler|v[eé]rifier|remplacer|graisser|nettoyer)\b", candidate, re.I):
                    rows.append({
                        "schedule_type": "unclassified",
                        "section": "text_review",
                        "operation_name": candidate,
                        "source_page": page_number,
                        "source_location": {"line": len(rows) + 1},
                        "condition_note": None,
                        "corrected_condition": None,
                        "review_state": "needs_review",
                        "confidence": "possible maintenance instruction; classify and correct manually",
                    })
        items = rows
        warnings.append("لم يُتعرف على مخطط صيانة موثوق؛ عُرضت صفوف المصدر الخام للمراجعة دون تفسير آلي للفواصل.")
    if not document.tables and not items:
        warnings.append("لم تُكتشف صفوف جدول؛ النص محفوظ ويمكن الرجوع إليه، لكن يلزم إدخال العمليات ومراجعتها يدويًا.")
    return {
        "title": title,
        "manufacturer": manufacturer,
        "document_version": version_match.group(1) if version_match else None,
        "text": text[:500_000],
        "items": items,
        "warnings": warnings,
        "metadata": {"ocr_used": document.ocr_used, "table_count": len(document.tables), "page_count": len(pages)},
    }


def create_catalog_import(db: Session, *, model_id: int, filename: str, data: bytes, user_id: int | None):
    model = db.get(EquipmentModel, model_id)
    if model is None:
        raise ValueError("طراز العتاد المحدد غير موجود.")
    parsed = parse_catalog(filename, data)
    digest = hashlib.sha256(data).hexdigest()
    existing = db.query(MaintenanceCatalogImport).filter_by(equipment_model_id=model_id, content_sha256=digest).first()
    if existing:
        return existing, True
    previous = db.query(MaintenanceCatalogImport).filter_by(equipment_model_id=model_id).order_by(MaintenanceCatalogImport.version_number.desc()).first()
    record = MaintenanceCatalogImport(
        equipment_model_id=model_id,
        version_number=(previous.version_number + 1 if previous else 1),
        manufacturer=parsed["manufacturer"], document_title=parsed["title"],
        document_version=parsed["document_version"], filename=Path(filename).name[:255],
        content_sha256=digest, file_type=Path(filename).suffix.lower(), source_file=data,
        extracted_text=parsed["text"], items_json=json.dumps(parsed["items"], ensure_ascii=False),
        warnings_json=json.dumps(parsed["warnings"], ensure_ascii=False), created_by_id=user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, False


def get_catalog_items(record: MaintenanceCatalogImport) -> list[dict]:
    try:
        items = json.loads(record.items_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return items if isinstance(items, list) else []


def update_catalog_item(db: Session, record: MaintenanceCatalogImport, index: int, changes: dict):
    items = get_catalog_items(record)
    if index < 0 or index >= len(items):
        raise IndexError("عنصر الكتالوج غير موجود.")
    allowed = {"operation_name", "review_state", "corrected_condition", "condition_note", "review_note", "group_id", "schedule_type"}
    for key, value in changes.items():
        if key in allowed:
            if isinstance(value, str):
                value = value.strip()
            items[index][key] = value
    if items[index].get("review_state") not in {"needs_review", "accepted", "rejected", "supplemental"}:
        raise ValueError("حالة المراجعة غير صالحة.")
    if not items[index].get("operation_name"):
        raise ValueError("اسم العملية مطلوب.")
    if items[index].get("review_state") == "accepted" and items[index].get("schedule_type") != "normal":
        raise ValueError("لا يمكن إضافة شرط إضافي أو غير مصنف كشرط أساسي؛ صنّف العملية أولًا.")
    if items[index].get("group_id") is not None and int(items[index]["group_id"]) < 1:
        raise ValueError("تصنيف العملية غير صالح.")
    if items[index].get("schedule_type") not in {"normal", "severe_conditions", "unclassified"}:
        raise ValueError("نوع الجدول غير صالح.")
    condition = items[index].get("corrected_condition")
    if condition is not None:
        if not isinstance(condition, dict):
            raise ValueError("شرط العملية يجب أن يكون كائنًا يحدد المحور والقيمة.")
        keys = {"interval_km", "interval_hours", "interval_days"}
        if set(condition) - keys or not any(condition.get(key) is not None for key in keys):
            raise ValueError("حدد فاصلًا موجبًا واحدًا على الأقل: كيلومترات أو ساعات أو أيام.")
        for key in keys:
            value = condition.get(key)
            if value is not None:
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("قيم فواصل الصيانة يجب أن تكون أرقامًا موجبة.") from exc
                if numeric_value <= 0:
                    raise ValueError("قيمة الفاصل يجب أن تكون أكبر من صفر.")
    record.items_json = json.dumps(items, ensure_ascii=False)
    record.status = "draft"
    record.reviewed_at = None
    db.commit()
    return items[index]


def compare_previous_version(db: Session, record: MaintenanceCatalogImport) -> dict:
    previous = db.query(MaintenanceCatalogImport).filter(
        MaintenanceCatalogImport.equipment_model_id == record.equipment_model_id,
        MaintenanceCatalogImport.version_number < record.version_number,
    ).order_by(MaintenanceCatalogImport.version_number.desc()).first()
    if previous is None:
        return {"previous_version": None, "added": len(get_catalog_items(record)), "removed": 0, "changed": 0}
    old = {f"{x.get('schedule_type')}|{x.get('section')}|{x.get('operation_name')}": x for x in get_catalog_items(previous)}
    new = {f"{x.get('schedule_type')}|{x.get('section')}|{x.get('operation_name')}": x for x in get_catalog_items(record)}
    common = old.keys() & new.keys()
    changed = sum(old[key] != new[key] for key in common)
    return {"previous_version": previous.version_number, "added": len(new.keys() - old.keys()), "removed": len(old.keys() - new.keys()), "changed": changed}
