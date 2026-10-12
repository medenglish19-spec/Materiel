from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from .extraction.extractor import extract_document
from .parsing.parser import parse_to_candidates
from .matching.matcher import match_against_definitions, _norm_key
from .normalization.normalizer import normalize_candidates
from .schemas import Candidate, ImportApplyItem
from app.modules.equipment_types.models import (
    EquipmentModel,
    EquipmentModelSpecValue,
    EquipmentModelSpecDefinition,
)
from app.modules.equipment_types.services import create_spec_definition
from app.modules.equipment_types.schemas import SpecDefinitionCreate


def preview_from_document(model_id: int, file_path: str | Path, mode: str = "extract", requested: Optional[List[str]] = None, db: Session | None = None) -> List[Candidate]:
    ex = extract_document(file_path)
    cands = parse_to_candidates(ex, model_id=model_id, mode=mode, requested=requested)
    if db is not None:
        m = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
        cands = match_against_definitions(db, cands, m)
    cands = normalize_candidates(cands)
    return cands


def preview_from_text(model_id: int, text: str, mode: str = "extract", requested: Optional[List[str]] = None, db: Session | None = None) -> List[Candidate]:
    from .extraction.extractor import ExtractedDocument

    exd = ExtractedDocument(text=text or "", tables=[], metadata={})
    cands = parse_to_candidates(exd, model_id=model_id, mode=mode, requested=requested)
    if db is not None:
        m = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
        cands = match_against_definitions(db, cands, m)
    cands = normalize_candidates(cands)
    return cands


class ApplyResult:
    """نتيجة تطبيق عنصر واحد."""

    def __init__(self, item: ImportApplyItem, status: str, reason: Optional[str] = None, definition_id: Optional[int] = None):
        self.item = item
        self.status = status  # إحدى STATUSES
        self.reason = reason
        self.definition_id = definition_id if definition_id is not None else item.definition_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name_found": self.item.name_found,
            "definition_id": self.definition_id,
            "status": self.status,
            "reason": self.reason,
        }


STATUSES = [
    "applied",
    "created_definition",
    "not_approved",
    "invalid_definition",
    "invalid_value",
    "unit_mismatch",
    "definition_out_of_scope",
    "definition_error",
]


def _normalize_unit(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = str(u).strip().lower()
    mapping = {
        "kw": "kW", "k.w.": "kW", "hp": "HP", "cv": "ch", "ch": "ch",
        "ton": "t", "tonne": "t", "t": "t", "g": "g", "kg": "kg",
        "mm": "mm", "cm": "cm", "m": "m", "l": "L", "cm3": "cm³", "cm³": "cm³",
        "v": "V", "a": "A", "ah": "Ah", "rpm": "rpm", "bar": "bar",
    }
    return mapping.get(u, u.upper() if len(u) <= 3 else u)


def _check_value_for_definition(defn: EquipmentModelSpecDefinition, value: str) -> Optional[str]:
    """نفس قواعد الإدخال اليدوي: رقم للنوع number، وإحدى الخيارات للنوع select. يرجع سبب الرفض أو None."""
    if defn.data_type == "number":
        try:
            float(value)
        except ValueError:
            return "not_a_number"
    elif defn.data_type == "select":
        allowed = {o.strip() for o in (defn.options or "").split(",") if o.strip()}
        if value not in allowed:
            return "not_in_options"
    return None


def apply_candidates(model_id: int, candidates: List[ImportApplyItem], db: Session, user_id: int | None = None) -> Dict[str, Any]:
    """يطبّق العناصر المعتمدة فقط.

    - نتائج التحقق لكل عنصر (غير معتمد، قيمة فارغة، تعريف غير صالح، خارج النطاق، وحدة مختلفة، خطأ تعريف)
      لا توقف بقية الدفعة.
    - أي استثناء غير متوقع يلغي الدفعة كلها (rollback) ثم يُرفع ليحوّله الراوتر إلى 500.
    - فرادة اسم التعريف عالمية في create_spec_definition، لذلك يُبحث بالاسم المطبَّع في كل التعريفات
      أولًا، ثم يُحكم بالنطاق (نوع النموذج أو None).
    """
    m = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
    if not m:
        raise ValueError("نموذج المعدة غير موجود")  # الراوتر يحوّله إلى 422

    summary: Dict[str, int] = {k: 0 for k in STATUSES}
    results: List[ApplyResult] = []

    def done(c: ImportApplyItem, status: str, reason: Optional[str] = None, defn: Optional[EquipmentModelSpecDefinition] = None) -> None:
        results.append(ApplyResult(c, status, reason or status, defn.id if defn is not None else None))
        summary[status] += 1

    type_id = m.equipment_type_id

    def in_scope(d: EquipmentModelSpecDefinition) -> bool:
        return d.equipment_type_id is None or d.equipment_type_id == type_id

    all_defs = db.query(EquipmentModelSpecDefinition).all()  # مرة واحدة للدفعة
    by_id = {d.id: d for d in all_defs}
    by_norm: Dict[str, EquipmentModelSpecDefinition] = {}
    for d in all_defs:
        nk = _norm_key(d.name or "")
        if not nk:
            continue
        cur = by_norm.get(nk)
        if cur is None or (in_scope(d) and not in_scope(cur)):
            by_norm[nk] = d  # عند تشابه الاسم نفضّل التعريف ضمن النطاق

    category_id = m.equipment_type.category_id if m.equipment_type is not None else None

    try:
        for c in candidates:
            if getattr(c, "ignored", False) or not getattr(c, "approved", False):
                done(c, "not_approved")
                continue

            use_edit = bool(getattr(c, "edited", False))
            raw_val = c.value_edited if use_edit and c.value_edited is not None else c.value
            unit = c.unit_edited if use_edit and c.unit_edited is not None else c.unit
            val = str(raw_val).strip() if raw_val is not None else ""
            if not val:
                done(c, "invalid_value", "empty_value")
                continue

            was_created = False
            defn: Optional[EquipmentModelSpecDefinition] = None

            if getattr(c, "is_new", False):
                name = (c.name_found or "").strip()
                if not name:
                    done(c, "invalid_definition", "empty_name")
                    continue
                nk = _norm_key(name)
                defn = by_norm.get(nk)
                if defn is None:
                    try:
                        defn = create_spec_definition(
                            db,
                            SpecDefinitionCreate(
                                name=name,
                                data_type="text",
                                unit=_normalize_unit(unit),
                                group_sort_order=0,
                                equipment_type_id=type_id,
                                category_id=category_id,
                            ),
                            commit=False,
                        )
                    except ValueError as exc:
                        done(c, "definition_error", str(exc))
                        continue
                    by_norm[nk] = defn
                    by_id[defn.id] = defn
                    was_created = True
            else:
                def_id = getattr(c, "definition_id", None)
                if def_id is None:
                    done(c, "invalid_definition", "missing_definition_id")
                    continue
                defn = by_id.get(def_id)
                if defn is None:
                    done(c, "invalid_definition", "definition_not_found")
                    continue

            if not was_created:
                if not in_scope(defn):
                    done(c, "definition_out_of_scope", f"الخاصية '{defn.name}' تابعة لنوع معدة آخر", defn)
                    continue
                def_unit = _normalize_unit(defn.unit)
                user_unit = _normalize_unit(unit)
                if def_unit and user_unit and def_unit != user_unit:
                    done(c, "unit_mismatch", f"unit_mismatch: def={defn.unit}, user={unit}", defn)
                    continue
                bad = _check_value_for_definition(defn, val)
                if bad:
                    done(c, "invalid_value", bad, defn)
                    continue

            ev = (
                db.query(EquipmentModelSpecValue)
                .filter(
                    EquipmentModelSpecValue.equipment_model_id == model_id,
                    EquipmentModelSpecValue.spec_definition_id == defn.id,
                )
                .first()
            )
            if ev:
                ev.value = val
            else:
                db.add(EquipmentModelSpecValue(equipment_model_id=model_id, spec_definition_id=defn.id, value=val))
            db.flush()  # ليراه العنصر التالي في الدفعة نفسها
            done(c, "created_definition" if was_created else "applied", None, defn)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"results": [r.to_dict() for r in results], "summary": summary}
