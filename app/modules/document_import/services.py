from typing import List, Optional
from ..schemas import Candidate
def preview_from_text(model_id: int, text: str, mode: str='extract', requested: Optional[List[str]]=None) -> List[Candidate]:
    return []
def apply_candidates(model_id: int, candidates: List[Candidate]) -> int:
    return 0
