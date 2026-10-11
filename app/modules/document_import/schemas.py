from pydantic import BaseModel, Field
from typing import Optional, List


class Candidate(BaseModel):
    name_found: Optional[str] = None
    canonical_name_ar: Optional[str] = None
    canonical_name_en: Optional[str] = None
    canonical_name_fr: Optional[str] = None
    value: str = ""
    unit: Optional[str] = None
    confidence: float = 0.0
    page: Optional[int] = None
    sheet: Optional[str] = None
    cell: Optional[str] = None
    source_ref: Optional[str] = None
    is_new: bool = True
    definition_id: Optional[int] = None
    approved: bool = False
    ignored: bool = False
    edited: bool = False
    value_edited: Optional[str] = None
    unit_edited: Optional[str] = None


class ImportPreviewResponse(BaseModel):
    candidates: List[Candidate] = Field(default_factory=list)


class ImportApplyItem(BaseModel):
    definition_id: Optional[int] = None
    name_found: Optional[str] = None
    value: str = ""
    unit: Optional[str] = None
    is_new: bool = True
    approved: bool = True
    ignored: bool = False
    edited: bool = False
    value_edited: Optional[str] = None
    unit_edited: Optional[str] = None
    source_ref: Optional[str] = None
    page: Optional[int] = None
    sheet: Optional[str] = None
    cell: Optional[str] = None
    confidence: float = 0.0


class ImportApplyRequest(BaseModel):
    model_id: int
    candidates: List[ImportApplyItem]
