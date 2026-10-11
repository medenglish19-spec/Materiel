from __future__ import annotations
import re


def _norm_val(v: str | None) -> str:
    if v is None:
        return ""
    v = str(v).replace("٬", ".").replace(",", ".")
    v = re.sub(r"\s+", "", v)
    return v


def normalize_candidate(c):
    if getattr(c, "edited", False):
        if c.value_edited is not None:
            c.value = c.value_edited
        if c.unit_edited is not None:
            c.unit = c.unit_edited
    c.value = _norm_val(c.value)
    if c.unit:
        u = str(c.unit).strip().lower()
        m = {
            "kw": "kW",
            "k.w.": "kW",
            "hp": "HP",
            "cv": "ch",
            "ch": "ch",
            "ton": "t",
            "tonne": "t",
            "t": "t",
            "g": "g",
            "mm": "mm",
            "cm": "cm",
            "m": "m",
            "l": "L",
            "cm3": "cm³",
            "cm³": "cm³",
            "v": "V",
            "a": "A",
            "ah": "Ah",
            "rpm": "rpm",
            "%": "%",
        }
        c.unit = m.get(u, str(c.unit).strip())
    return c


def normalize_candidates(lst):
    return [normalize_candidate(x) for x in lst]
