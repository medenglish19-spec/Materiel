from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from .extraction.extractor import extract_document
from .parsing.parser import parse_to_candidates
from .matching.matcher import match_against_definitions
from .normalization.normalizer import normalize_candidates
from .schemas import Candidate, ImportApplyItem
from app.modules.equipment_types.models import EquipmentModel, EquipmentModelSpecValue


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


def apply_candidates(model_id: int, candidates: List[ImportApplyItem], db: Session, user_id: int | None = None) -> Dict[str, int]:
    added = 0
    skipped_new = 0
    skipped_ignored = 0
    skipped_no_def = 0
    m = db.query(EquipmentModel).filter(EquipmentModel.id == model_id).first()
    if not m:
        return {"added": 0, "skipped_new": 0, "skipped_ignored": 0, "skipped_no_def": 0}
    for c in candidates:
        if getattr(c, "ignored", False):
            skipped_ignored += 1
            continue
        if not getattr(c, "approved", False):
            skipped_ignored += 1
            continue
        if not getattr(c, "definition_id", None) or getattr(c, "is_new", True):
            skipped_new += 1
            continue
        val = c.value_edited if getattr(c, "edited", False) and c.value_edited is not None else c.value
        unit = c.unit_edited if getattr(c, "edited", False) and c.unit_edited is not None else c.unit
        if not c.approved:
            skipped_ignored += 1
            continue
        if not c.definition_id or c.is_new:
            skipped_new += 1
            continue
        ev = (
            db.query(EquipmentModelSpecValue)
            .filter(EquipmentModelSpecValue.equipment_model_id == model_id, EquipmentModelSpecValue.spec_definition_id == c.definition_id)
            .first()
        )
        if ev:
            ev.value = str(val) if val is not None else ""
        else:
            ev = EquipmentModelSpecValue(equipment_model_id=model_id, spec_definition_id=c.definition_id, value=str(val) if val is not None else "")
            db.add(ev)
        added += 1
    db.commit()
    return {"added": added, "skipped_new": skipped_new, "skipped_ignored": skipped_ignored, "skipped_no_def": skipped_no_def}