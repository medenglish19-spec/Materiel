from typing import Optional
from pydantic import BaseModel,Field,ConfigDict,field_validator
class Candidate(BaseModel):
 model_config=ConfigDict(extra="forbid")
 canonical_name_ar:Optional[str]=None;canonical_name_en:Optional[str]=None;canonical_name_fr:Optional[str]=None
 source_name:str="";value:str="";unit:Optional[str]=None;confidence:float=Field(default=0,ge=0,le=1)
 page:Optional[int]=None;sheet:Optional[str]=None;cell:Optional[str]=None;source_ref:Optional[str]=None
 is_new:bool=True;definition_id:Optional[int]=None;approved:bool=False;ignored:bool=False;value_edited:bool=False;unit_edited:bool=False
 @field_validator("value")
 @classmethod
 def value_limit(cls,v):
  v=v.strip()
  if len(v)>255:raise ValueError("قيمة الخاصية تتجاوز 255 حرفًا")
  return v
class ImportPreviewResponse(BaseModel):
 candidates:list[Candidate]=Field(default_factory=list);warnings:list[str]=Field(default_factory=list);filename:str="";model_id:int
class ImportApplyRequest(BaseModel):
 model_id:int;candidates:list[Candidate]=Field(min_length=1,max_length=500)
class ImportApplyResponse(BaseModel):
 applied:int;skipped:int;message:str
