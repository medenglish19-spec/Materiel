import re
from ..schemas import Candidate
from ..normalization.normalizer import normalize_value
PAIR=re.compile(r"^\s*([^:=：\t]{2,100}?)\s*(?:[:=：]|\t+)\s*(.{1,255}?)\s*$")
NUMBER=re.compile(r"^([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*([\w%°/³².-]+)?$")
def parse_extracted_document(doc):
 out=[]
 for i,line in enumerate((doc.text or "").splitlines(),1):
  m=PAIR.match(line)
  if m:
   name,value=map(str.strip,m.groups());u=None;n=NUMBER.match(value)
   if n and n.group(2):value,u=n.groups()
   if name and value:out.append(Candidate(source_name=name,canonical_name_ar=name,value=normalize_value(value),unit=u,confidence=.55,source_ref=f"line:{i}"))
 for table in getattr(doc,"tables",[]):
  for i,row in enumerate(table.rows,1):
   if len(row)<2:continue
   name,value=normalize_value(row[0]),normalize_value(row[1])
   if not name or not value or name.casefold() in {"الخاصية","البيان","property","specification","caractéristique"}:continue
   u=None;n=NUMBER.match(value)
   if n and n.group(2):value,u=n.groups()
   out.append(Candidate(source_name=name,canonical_name_ar=name,value=value,unit=u,confidence=.62,sheet=table.name,cell=f"row:{i}",source_ref=f"{table.name or 'table'}:row:{i}",page=table.page))
 seen=set();unique=[]
 for c in out:
  key=(c.source_name.casefold(),c.value.casefold())
  if key not in seen:seen.add(key);unique.append(c)
 return unique
