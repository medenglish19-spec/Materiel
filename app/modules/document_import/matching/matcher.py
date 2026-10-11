from __future__ import annotations
import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import difflib

from ..schemas import Candidate
from app.modules.equipment_types.models import EquipmentModelSpecDefinition

_FUZZ_AVAILABLE = False
try:
    from rapidfuzz import fuzz

    _FUZZ_AVAILABLE = True
except ImportError:
    fuzz = None


class _SeqFuzz:
    @staticmethod
    def _norm(s: str) -> str:
        return (s or "").strip()

    @staticmethod
    def _ratio(a: str, b: str) -> int:
        a = _SeqFuzz._norm(a)
        b = _SeqFuzz._norm(b)
        if not a or not b:
            return 0
        return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100.0))

    @staticmethod
    def ratio(a: str, b: str) -> int:
        return _SeqFuzz._ratio(a, b)

    @staticmethod
    def partial_ratio(a: str, b: str) -> int:
        a = _SeqFuzz._norm(a).lower()
        b = _SeqFuzz._norm(b).lower()
        if not a or not b:
            return 0
        if len(a) <= len(b):
            short, long_ = a, b
        else:
            short, long_ = b, a
        best = 0.0
        slen = len(short)
        llen = len(long_)
        for i in range(llen - slen + 1):
            r = difflib.SequenceMatcher(None, short, long_[i : i + slen]).ratio()
            if r > best:
                best = r
            if best >= 0.99:
                break
        if best < 0.7:
            ta = set(re.findall(r"[^\W\d]+", a))
            tb = set(re.findall(r"[^\W\d]+", b))
            if ta and tb:
                inter = ta & tb
                if inter:
                    best = max(best, len(inter) / len(ta | tb))
        return int(round(best * 100.0))

    @staticmethod
    def token_sort_ratio(a: str, b: str) -> int:
        def _tok(s: str):
            tokens = re.findall(r"[^\W\d]+|[A-Za-z0-9]+", (s or "").lower())
            tokens = [t for t in tokens if t]
            tokens.sort()
            return " ".join(tokens)

        return _SeqFuzz._ratio(_tok(a), _tok(b))

    @staticmethod
    def token_set_ratio(a: str, b: str) -> int:
        def _tokset(s: str):
            tokens = re.findall(r"[^\W\d]+|[A-Za-z0-9]+", (s or "").lower())
            return {t for t in tokens if t}

        ta = _tokset(a)
        tb = _tokset(b)
        if not ta or not tb:
            return _SeqFuzz._ratio(a, b)
        inter = ta & tb
        if inter:
            s_inter = " ".join(sorted(inter))
            s_ta = " ".join(sorted(ta))
            s_tb = " ".join(sorted(tb))
            return max(
                _SeqFuzz._ratio(s_inter, s_ta),
                _SeqFuzz._ratio(s_inter, s_tb),
                _SeqFuzz._ratio(s_ta, s_tb),
            )
        return _SeqFuzz.token_sort_ratio(a, b)


if not _FUZZ_AVAILABLE:
    fuzz = _SeqFuzz()  # type: ignore[assignment]

SYNONYMS: Dict[str, List[str]] = {
    "engine_power": ["قدرة المحرك", "قوة المحرك", "قدرة المحرك (kw)", "قدرة المحرك (kW)", "Power", "Engine power", "Brake power", "Puissance moteur", "puissance"],
    "engine_displacement": ["سعة المحرك", "حجم المحرك", "الإزاحة", "Displacement", "Engine displacement", "Cylindrée", "Swept volume"],
    "weight": ["الوزن", "وزن", "الوزن الإجمالي", "الوزن الكلي", "Weight", "Gross weight", "Kerb weight", "Poids", "Poids total"],
    "transmission_type": ["نوع ناقل الحركة", "ناقل الحركة", "علبة التروس", "Transmission", "Transmission type", "Gearbox", "Boîte de vitesses"],
    "length": ["الطول", "طول", "Length", "Overall length", "Longueur"],
    "width": ["العرض", "عرض", "Width", "Overall width", "Largeur"],
    "height": ["الارتفاع", "ارتفاع", "Height", "Overall height", "Hauteur"],
    "wheelbase": ["قاعدة العجلات", "Wheelbase", "Empattement"],
    "fuel_tank": ["خزان الوقود", "سعة خزان الوقود", "Fuel tank", "Fuel capacity", "Réservoir carburant"],
    "cooling_system": ["نظام التبريد", "نظام التبريد السائل", "Cooling system", "Liquid cooling", "Refroidissement"],
    "max_speed": ["السرعة القصوى", "Vitesse maximale", "Maximum speed", "Max speed"],
    "torque": ["العزم", "Torque", "Engine torque", "Couple"],
    "cylinders": ["عدد الأسطوانات", "Cylinders", "Number of cylinders", "Cylindres"],
}


def _norm_key(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^\w\u0600-\u06FF\u00C0-\u017F]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_against_definitions(db: Session, candidates: List[Candidate]) -> List[Candidate]:
    defs = (
        db.query(EquipmentModelSpecDefinition)
        .order_by(
            EquipmentModelSpecDefinition.group_sort_order,
            EquipmentModelSpecDefinition.group_name,
            EquipmentModelSpecDefinition.sort_order,
            EquipmentModelSpecDefinition.name,
        )
        .all()
    )

    idx = []
    for d in defs:
        names = []
        if d.name:
            names.append(d.name)
        if getattr(d, "code", None):
            names.append(d.code)
        nk = _norm_key(d.name or "")
        for k, vlist in SYNONYMS.items():
            for v in vlist:
                if _norm_key(v) == nk or fuzz.ratio(_norm_key(v), nk) > 85:
                    names.extend(vlist)
                    break
        nklist = []
        for x in names:
            nklist.append(_norm_key(x))
            nklist.append(_norm_key(x.replace("موتور", "").replace("moteur", "")))
        nklist = [n for n in nklist if n]
        nklist = list(dict.fromkeys(nklist))
        idx.append({"d": d, "names": nklist})

    res = []
    for c in candidates:
        nf = c.name_found or ""
        nk = _norm_key(nf)
        best = None
        bestsc = 0
        for e in idx:
            for en in e["names"]:
                if not en:
                    continue
                sc = max(fuzz.ratio(nk, en), fuzz.partial_ratio(nk, en), fuzz.token_set_ratio(nk, en))
                if sc > bestsc:
                    bestsc = sc
                    best = e
                if bestsc >= 95:
                    break
            if bestsc >= 95:
                break
        if best and bestsc >= 85:
            d = best["d"]
            c.definition_id = d.id
            c.is_new = False
            c.canonical_name_ar = d.name if any(ord(ch) >= 0x600 and ord(ch) <= 0x6FF for ch in (d.name or "")) else (c.canonical_name_ar or d.name)
            c.canonical_name_en = d.name if re.search(r"[A-Za-z]", d.name or "") else (c.canonical_name_en or d.name)
            c.canonical_name_fr = d.name
            c.confidence = max(getattr(c, "confidence", 0.0) or 0.0, float(bestsc) / 100.0)
        else:
            c.is_new = True
        res.append(c)
    return res
