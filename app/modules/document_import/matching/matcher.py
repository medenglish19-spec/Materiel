from typing import List, Optional, Dict, Any
from ..schemas import Candidate

# Minimal offline synonym map (ar/fr/en) for common engine specs
SYNONYMS: Dict[str, List[str]] = {
    'engine_power': ['قدرة المحرك','قوة المحرك','Puissance moteur','Engine power','Power','puissance','engine power'],
    'engine_displacement': ['سعة المحرك','حجم المحرك','Cylindrée','Engine displacement','Displacement','cylindree'],
    'weight': ['الوزن','وزن','Poids','Weight','poids total','Gross weight'],
    'transmission_type': ['نوع ناقل الحركة','ناقل الحركة','Type de transmission','Transmission type','Gearbox','Transmission'],
    'length': ['الطول','طول','Longueur','Length'],
    'cooling_system': ['نظام التبريد','تبريد','Système de refroidissement','Cooling system','Liquid cooling'],
}
