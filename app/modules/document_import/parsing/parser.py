from __future__ import annotations
import re
from typing import List, Optional
from ..schemas import Candidate
from ..extraction.extractor import ExtractedDocument

UNIT_PAT = r"(kW|KW|kw|HP|hp|ch|CV|cv|kg|Kg|KG|t|T|ton|g|mm|cm|m|M|L|l|cm³|cm3|V|A|Ah|rpm|tr/min|bar|Pa|psi|°C|°F|%|pcs|units|unit)"
SEP = r"[:=\-–\—]"

NAME_PAT = r"([^\d:;=\-\(\)\[\]\t\r\n]{2,80})"


def _norm(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _split_unit(v: str) -> tuple[str, Optional[str]]:
    v2 = _norm(v)
    m = re.search(rf"^\s*([+-]?\d+[.,]?\d*)\s*({UNIT_PAT})\s*$", v2, re.I)
    if m:
        return m.group(1).replace(",", "."), m.group(2).lower()
    m = re.search(rf"([+-]?\d+[.,]?\d*)\s*({UNIT_PAT})\b", v2, re.I)
    if m:
        return m.group(1).replace(",", "."), m.group(2).lower()
    return v2, None


def parse_to_candidates(extracted: ExtractedDocument, model_id: int, mode: str = "extract", requested: Optional[List[str]] = None) -> List[Candidate]:
    cands: List[Candidate] = []
    requested_list = [r.strip().lower() for r in (requested or []) if r.strip()]

    text = extracted.text or ""

    # pattern name : value unit
    pat1 = re.compile(rf"{NAME_PAT}\s*{SEP}\s*([^\n;]+)", re.I | re.M | re.U)
    for m in pat1.finditer(text):
        nm = _norm(m.group(1))
        val = _norm(m.group(2))
        if not nm or len(nm) < 2:
            continue
        v, u = _split_unit(val)
        cands.append(Candidate(name_found=nm, value=v or val, unit=u, source_ref="Text", confidence=0.92))

    # reverse
    pat2 = re.compile(rf"([+-]?\d+[.,]?\d*\s*{UNIT_PAT})\b\s+{NAME_PAT}", re.I | re.U)
    for m in pat2.finditer(text):
        v, u = _split_unit(_norm(m.group(1)))
        nm = _norm(m.group(3))
        if nm and len(nm) >= 2:
            cands.append(Candidate(name_found=nm, value=v, unit=u, source_ref="Text", confidence=0.9))

    for i, tb in enumerate(extracted.tables):
        for r, row in enumerate(tb.rows):
            if len(row) < 2:
                continue
            nm = _norm(str(row[0]))
            val = _norm(" ".join(str(x) for x in row[1:] if x not in (None, "")))
            if not nm or len(nm) < 2:
                continue
            v, u = _split_unit(val)
            ref = f"Table:{getattr(tb,'name',str(i))} R{r+1}"
            cands.append(Candidate(name_found=nm, value=v or val, unit=u, source_ref=ref, confidence=0.93, sheet=getattr(tb, "name", None)))

    if mode == "specific" and requested_list:
        def ok(x):
            nf = (x.name_found or "").lower()
            return any(r in nf or nf in r for r in requested_list)

        cands = [x for x in cands if ok(x)]

    seen = set()
    out = []
    for x in cands:
        key = ((x.name_found or "").lower(), (x.value or ""), (x.unit or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out
