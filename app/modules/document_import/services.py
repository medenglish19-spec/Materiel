from sqlalchemy.orm import Session
from app.modules.equipment_types.models import EquipmentModel,EquipmentModelSpecDefinition,EquipmentModelSpecValue
from .schemas import Candidate
from .extraction.extractor import extract_document
from .parsing.parser import parse_extracted_document
from .matching.matcher import match_against_definitions
from .normalization.normalizer import normalize_value,normalize_text
def preview_from_document(db:Session,model_id:int,filename:str,content:bytes,mode="extract",requested=None):
 if db.query(EquipmentModel.id).filter_by(id=model_id).first() is None:raise ValueError("الطراز المحدد غير موجود")
 if mode not in {"extract","specific"}:raise ValueError("طريقة الجلب غير صالحة")
 doc=extract_document(filename,content);items=parse_extracted_document(doc);warnings=[]
 if mode=="specific":
  terms=[normalize_text(x) for x in (requested or []) if normalize_text(x)]
  if not terms:raise ValueError("أدخل أسماء الخصائص المطلوبة")
  items=[c for c in items if any(t in normalize_text(c.source_name) or normalize_text(c.source_name) in t for t in terms)]
 if not items:warnings.append("لم يتم العثور على خصائص بصيغة اسم وقيمة واضحة.")
 items=match_against_definitions(db,items,model_id)
 if doc.ocr_used:warnings.append("استُخدم OCR محلي؛ راجع النتائج بعناية.")
 return items,warnings
def apply_candidates(db:Session,model_id:int,candidates:list[Candidate]):
 model=db.query(EquipmentModel).filter_by(id=model_id).with_for_update().first()
 if model is None:raise ValueError("الطراز المحدد غير موجود")
 approved=[c for c in candidates if c.approved and not c.ignored];skipped=len(candidates)-len(approved)
 if not approved:raise ValueError("لم تعتمد أي خاصية للحفظ")
 try:
  for c in approved:
   if c.is_new or c.definition_id is None:raise ValueError("لا يمكن حفظ خاصية غير مطابقة لتعريف موجود في المكتبة")
   d=db.query(EquipmentModelSpecDefinition).filter_by(id=c.definition_id).first()
   if d is None:raise ValueError("تعريف الخاصية لم يعد موجودًا؛ أعد المعاينة")
   if d.equipment_type_id not in (None,model.equipment_type_id):raise ValueError("تعريف الخاصية لا يتبع نوع العتاد للطراز")
   value=normalize_value(c.value)
   if not value:raise ValueError("قيمة الخاصية لا يمكن أن تكون فارغة")
   row=db.query(EquipmentModelSpecValue).filter_by(equipment_model_id=model_id,spec_definition_id=d.id).first()
   if row:row.value=value
   else:db.add(EquipmentModelSpecValue(equipment_model_id=model_id,spec_definition_id=d.id,value=value))
  db.commit()
 except Exception:
  db.rollback();raise
 return len(approved),skipped
