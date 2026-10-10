from pydantic import BaseModel, Field
from typing import Optional, List
class Candidate(BaseModel):
    canonical_name_ar: Optional[str]=None
    canonical_name_en: Optional[str]=None
    canonical_name_fr: Optional[str]=None
    value: str=''
    unit: Optional[str]=None
    confidence: float=0.0
    page: Optional[int]=None
    sheet: Optional[str]=None
    cell: Optional[str]=None
    source_ref: Optional[str]=None
    is_new: bool=True
    definition_id: Optional[int]=None
class ImportPreviewResponse(BaseModel):
    candidates: List[Candidate]=Field(default_factory=list)
