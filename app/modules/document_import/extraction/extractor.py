from pathlib import Path
from typing import Any,Dict,List,Optional,Union
class ExtractedTable:
    def __init__(self,rows=None,name=None,page=None):
        self.rows=rows or []; self.name=name; self.page=page
class ExtractedDocument:
    def __init__(self,text='',tables=None,metadata=None,ocr_used=False,ocr_engine=None):
        self.text=text or ''; self.tables=tables or []; self.metadata=metadata or {}; self.ocr_used=ocr_used; self.ocr_engine=ocr_engine
