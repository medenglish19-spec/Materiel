from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from app.modules.equipment_types.models import EquipmentModel,EquipmentModelSpecDefinition
from ..schemas import Candidate
from ..normalization.normalizer import normalize_text
SYNONYMS={"engine_power":["قدرة المحرك","قوة المحرك","Puissance moteur","Engine power","Power"],"engine_displacement":["سعة المحرك","حجم المحرك","Cylindrée","Engine displacement","Displacement"],"weight":["الوزن","Poids","Weight","Gross weight"],"transmission_type":["نوع ناقل الحركة","Type de transmission","Transmission type","Gearbox"],"length":["الطول","Longueur","Length"],"width":["العرض","Largeur","Width"],"height":["الارتفاع","Hauteur","Height"],"fuel_type":["نوع الوقود","Type de carburant","Fuel type"],"cooling_system":["نظام التبريد","Système de refroidissement","Cooling system"]}
def match_against_definitions(db:Session,candidates:list[Candidate],model_id:int)->list[Candidate]:
 model=db.query(EquipmentModel).filter_by(id=model_id).first()
 if model is None:raise ValueError("الطراز المحدد غير موجود")
 defs=db.query(EquipmentModelSpecDefinition).filter((EquipmentModelSpecDefinition.equipment_type_id.is_(None))|(EquipmentModelSpecDefinition.equipment_type_id==model.equipment_type_id)).all()
 for c in candidates:
  src=normalize_text(c.source_name or c.canonical_name_ar or c.canonical_name_fr or c.canonical_name_en);best=None;score=0
  for d in defs:
   labels={normalize_text(d.name),normalize_text(d.code or "")}
   code=(d.code or "").strip().casefold()
   labels.update(normalize_text(x) for x in SYNONYMS.get(code,[]))
   cur=max((1 if src==x else SequenceMatcher(None,src,x).ratio() for x in labels if x),default=0)
   if cur>score:best,score=d,cur
  if best and score>=.78:c.definition_id=best.id;c.is_new=False;c.canonical_name_ar=best.name;c.unit=best.unit;c.confidence=max(c.confidence,round(score,3))
  else:c.definition_id=None;c.is_new=True
 return candidates
