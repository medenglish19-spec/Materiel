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


def preview_from_document(model_id: int, file_path: str | Path, mode: str = "extract", requested: Optional[List[str]] = None, db: Session | None = None) -> List[Candidate]:
    ex = extract_document(file_path)
    cands = parse_to_candidates(ex, model_id=model_id, mode=mode, requested=requested)
    if db is not None:
        cands = match_against_definitions(db, cands)
    cands = normalize_candidates(cands)
    return cands


def preview_from_text(model_id: int, text: str, mode: str = "extract", requested: Optional[List[str]] = None, db: Session | None = None) -> List[Candidate]:
    from .extraction.extractor import ExtractedDocument

    exd = ExtractedDocument(text=text or "", tables=[], metadata={})
    cands = parse_to_candidates(exd, model_id=model_id, mode=mode, requested=requested)
    if db is not None:
        cands = match_against_definitions(db, cands)
    cands = normalize_candidates(cands)
    return cands


class ApplyResult:
    """نتيجة تطبيق عنصر واحد."""
    def __init__(self, item: ImportApplyItem, status: str, reason: Optional[str] = None):
        self.item = item
        self.status = status  # applied / created_definition / not_approved / invalid_definition / skipped
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name_found": self.item.name_found,
            "definition_id": self.item.definition_id,
            "status": self.status,
            "reason": self.reason,
        }


def _find_or_create_definition(db: Session, name: str, unit: Optional[str], existing_defs_cache: Dict[str, EquipmentModelSpecDefinition]) -> tuple[EquipmentModelSpecDefinition, bool]:
    """
    يبحث عن تعريف مطابق بالاسم المطبّع، أو ينشئ جديداً.
    يمنع التكرار داخل الدفعة عبر cache.
    Returns: (definition, was_created)
    """
    nk = _norm_key(name)
    if nk in existing_defs_cache:
        return existing_defs_cache[nk], False
    
    # بحث في قاعدة البيانات
    defs = db.query(EquipmentModelSpecDefinition).all()
    for d in defs:
        if _norm_key(d.name or "") == nk:
            existing_defs_cache[nk] = d
            return d, False
    
    # إنشاء جديد
    new_def = EquipmentModelSpecDefinition(
        name=name,
        code=nk,
        data_type="text",
        unit=unit,
        sort_order=0,
        group_name=None,
        group_sort_order=0,
        equipment_type_id=None,
        category_id=None,
    )
    db.add(new_def)
    db.flush()
    existing_defs_cache[nk] = new_def
    return new_def, True


def apply_candidates(model_id: int, candidates: List[ImportApplyItem], db: Session, user_id: int | None = None) -> Dict[str, Any]:
    m = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
    if not m:
        return {
            "results": [],
            "summary": {"applied": 0, "created_definition": 0, "not_approved": 0, "invalid_definition": 0, "skipped": 0}
        }
    
    results: List[ApplyResult] = []
    created_defs_cache: Dict[str, EquipmentModelSpecDefinition] = {}
    summary = {"applied": 0, "created_definition": 0, "not_approved": 0, "invalid_definition": 0, "skipped": 0}
    
    for c in candidates:
        # غير معتمد أو متجاهل
        if getattr(c, "ignored", False) or not getattr(c, "approved", False):
            results.append(ApplyResult(c, "not_approved", "not_approved"))
            summary["not_approved"] += 1
            continue
        
        # تحديد التعريف
        defn: Optional[EquipmentModelSpecDefinition] = None
        status = "applied"
        
        if getattr(c, "is_new", False):
            # عنصر جديد معتمد - البحث أو إنشاء تعريف
            name = c.name_found or ""
            unit = c.unit
            if not name:
                results.append(ApplyResult(c, "invalid_definition", "empty_name"))
                summary["invalid_definition"] += 1
                continue
            defn, was_created = _find_or_create_definition(db, name, unit, created_defs_cache)
            if was_created:
                status = "created_definition"
                summary["created_definition"] += 1
            else:
                status = "applied"
                summary["applied"] += 1
        else:
            # عنصر موجود - التحقق من التعريف
            def_id = getattr(c, "definition_id", None)
            if def_id is None:
                results.append(ApplyResult(c, "invalid_definition", "missing_definition_id"))
                summary["invalid_definition"] += 1
                continue
            defn = db.query(EquipmentModelSpecDefinition).filter(EquipmentModelSpecDefinition.id == def_id).first()
            if not defn:
                results.append(ApplyResult(c, "invalid_definition", "definition_not_found"))
                summary["invalid_definition"] += 1
                continue
            summary["applied"] += 1
        
        # القيمة والوحدة
        val = c.value_edited if getattr(c, "edited", False) and c.value_edited is not None else c.value
        unit = c.unit_edited if getattr(c, "edited", False) and c.unit_edited is not None else c.unit
        
        # upsert EquipmentModelSpecValue
        ev = (
            db.query(EquipmentModelSpecValue)
            .filter(EquipmentModelSpecValue.equipment_model_id == model_id, EquipmentModelSpecValue.spec_definition_id == defn.id)
            .first()
        )
        if ev:
            ev.value = str(val) if val is not None else ""
            if unit is not None:
                ev.unit = unit  # type: ignore[attr-defined]
        else:
            ev = EquipmentModelSpecValue(equipment_model_id=model_id, spec_definition_id=defn.id, value=str(val) if val is not None else "")
            if unit is not None:
                try:
                    setattr(ev, "unit", unit)
                except Exception:
                    pass
            db.add(ev)
            db.flush()  # ensure visibility for subsequent items in same batch
        
        results.append(ApplyResult(c, status))
    
    db.commit()
    
    return {
        "results": [r.to_dict() for r in results],
        "summary": summary
    }