from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

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
    def __init__(self, item: ImportApplyItem, status: str, reason: Optional[str] = None):
        self.item = item
        self.status = status  # applied / created_definition / not_approved / invalid_definition / unit_mismatch / invalid_value / definition_out_of_scope / definition_error / skipped
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name_found": self.item.name_found,
            "definition_id": self.item.definition_id,
            "status": self.status,
            "reason": self.reason,
        }


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


def _load_defs_for_model(db: Session, model: EquipmentModel) -> Dict[str, EquipmentModelSpecDefinition]:
    """
    تحميل التعريفات المتاحة للنموذج: تعريفات نوع المعدة + التعريفات العامة (بدون نوع).
    Returns: dict mapping normalized_name -> definition
    """
    m_type = getattr(model, 'equipment_type', None)
    if not m_type:
        # نموذج بدون نوع - إرجاع التعريفات العامة فقط
        defs = db.query(EquipmentModelSpecDefinition).filter(
            EquipmentModelSpecDefinition.equipment_type_id.is_(None)
        ).all()
    else:
        # تعريفات النوع + التعريفات العامة
        etype_id = getattr(m_type, 'id', None)
        if etype_id is None:
            defs = db.query(EquipmentModelSpecDefinition).filter(
                EquipmentModelSpecDefinition.equipment_type_id.is_(None)
            ).all()
        else:
            defs = db.query(EquipmentModelSpecDefinition).filter(
                or_(
                    EquipmentModelSpecDefinition.equipment_type_id == etype_id,
                    EquipmentModelSpecDefinition.equipment_type_id.is_(None)
                )
            ).all()
    
    result = {}
    for d in defs:
        nk = _norm_key(d.name or "")
        if nk and nk not in result:
            result[nk] = d
    return result


def _find_or_create_definition(db: Session, name: str, unit: Optional[str], existing_defs_cache: Dict[str, EquipmentModelSpecDefinition], model: EquipmentModel) -> tuple[EquipmentModelSpecDefinition, bool]:
    """
    يبحث عن تعريف مطابق بالاسم المطبّع، أو ينشئ جديداً عبر create_spec_definition.
    يمنع التكرار داخل الدفعة عبر cache.
    Returns: (definition, was_created)
    """
    nk = _norm_key(name)
    if nk in existing_defs_cache:
        return existing_defs_cache[nk], False
    
    # بحث في قاعدة البيانات - البحث في التعريفات ذات الصلة بالنموذج
    defs = db.query(EquipmentModelSpecDefinition).all()
    for d in defs:
        if _norm_key(d.name or "") == nk:
            existing_defs_cache[nk] = d
            return d, False
    
    # إنشاء جديد عبر الدالة الموجودة
    model_type = db.query(EquipmentModel).filter(EquipmentModel.id == model.id).first()
    if not model_type:
        raise ValueError(f"Model with id {model.id} not found")
    
    eq_type = model_type.equipment_type
    if not eq_type:
        raise ValueError(f"Equipment type not found for model {model.id}")
    
    data = SpecDefinitionCreate(
        name=name,
        code=_norm_key(name),
        data_type="text",
        unit=_normalize_unit(unit),
        group_name="التعريف الفني",
        group_sort_order=0,
        equipment_type_id=model_type.equipment_type_id,
        category_id=eq_type.category_id,
    )
    new_def = create_spec_definition(db, data, commit=False)
    existing_defs_cache[nk] = new_def
    return new_def, True


def apply_candidates(model_id: int, candidates: List[ImportApplyItem], db: Session, user_id: int | None = None) -> Dict[str, Any]:
    m = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
    if not m:
        raise ValueError("نموذج المعدة غير موجود")  # الراوتر يحوّله إلى 404/422
    
    STATUSES = ["applied", "created_definition", "not_approved", "invalid_definition",
                "invalid_value", "unit_mismatch", "definition_out_of_scope", "definition_error"]
    
    summary = {k: 0 for k in STATUSES}
    results = []
    
    # Pre-load definitions for this model to avoid N+1 queries
    defs_for_model = _load_defs_for_model(db, m)
    
    results: List[ApplyResult] = []
    created_defs_cache: Dict[str, EquipmentModelSpecDefinition] = {}
    # Initialize cache with pre-loaded definitions
    created_defs_cache.update(defs_for_model)
    # Track newly created definition keys in this batch
    newly_created_keys: set[str] = set()
    summary = {k: 0 for k in STATUSES}
    
    try:
        for c in candidates:
            # غير معتمد أو متجاهل
            if getattr(c, "ignored", False) or not getattr(c, "approved", False):
                results.append(ApplyResult(c, "not_approved", "not_approved"))
                summary["not_approved"] += 1
                continue
            
            # التحقق من قيمة فارغة
            val = c.value_edited if getattr(c, "edited", False) and c.value_edited is not None else c.value
            if not val or not str(val).strip():
                results.append(ApplyResult(c, "invalid_value", "empty_value"))
                summary["invalid_value"] += 1
                continue
            
            # تحديد التعريف
            defn: Optional[EquipmentModelSpecDefinition] = None
            status = "applied"
            was_created = False
            
            if getattr(c, "is_new", False):
                # عنصر جديد معتمد - البحث أو إنشاء تعريف
                name = c.name_found or ""
                if not name:
                    results.append(ApplyResult(c, "invalid_definition", "empty_name"))
                    summary["invalid_definition"] += 1
                    continue
                defn, was_created = _find_or_create_definition(db, name, c.unit, created_defs_cache, m)
                if was_created:
                    status = "created_definition"
                else:
                    status = "applied"
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
            
            # القيمة والوحدة
            val = c.value_edited if getattr(c, "edited", False) and c.value_edited is not None else c.value
            unit = c.unit_edited if getattr(c, "edited", False) and c.unit_edited is not None else c.unit
            
            # تحقق من مطابقة الوحدة للتعريفات الموجودة (لكل التعريفات الموجودة، سواء كانت is_new=False أو is_new=True لكن وجدت تعريف مطابق)
            if not getattr(c, "is_new", False):
                # للتعريفات الموجودة: تحقق من توافق الوحدة
                def_unit = _normalize_unit(defn.unit) if defn.unit else None
                user_unit = _normalize_unit(unit) if unit else None
                if def_unit and user_unit and def_unit != user_unit:
                    results.append(ApplyResult(c, "unit_mismatch", f"unit_mismatch: def={defn.unit}, user={unit}"))
                    summary["unit_mismatch"] += 1
                    continue
            
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
            
            # تحديث العدادات بعد الحفظ الناجح
            if was_created:
                summary["created_definition"] += 1
            else:
                summary["applied"] += 1
        
        db.commit()
        
        return {
            "results": [r.to_dict() for r in results],
            "summary": summary
        }
    except ValueError as e:
        # ValueError من create_spec_definition أو _find_or_create_definition (نموذج/نوع مفقود)
        db.rollback()
        return {
            "results": [],
            "summary": {"applied": 0, "created_definition": 0, "not_approved": 0, "invalid_definition": 0, "unit_mismatch": 0, "invalid_value": 0, "skipped": 0},
            "error": str(e)
        }
    except Exception:
        db.rollback()
        raise