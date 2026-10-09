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
        # also try word-based
        if best < 0.7:
            # check tokens
            ta = set(re.findall(r"[^\W\d]+", a))
            tb = set(re.findall(r"[^\W\d]+", b))
            if ta and tb:
                inter = ta & tb
                if inter:
                    best = max(best, len(inter) / len(ta | tb))  # jaccard
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
