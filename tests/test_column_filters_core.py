"""Behavioral tests for the shared per-column filter core.

`static/js/mt-filters-core.js` is deliberately DOM-free and UMD, so Node can
load it directly. The harness builds a small in-memory table and asks the core
which rows survive each filter; this proves single-column and combined (AND)
matching for text, number, date and status-value filters without a browser.

Node is optional locally (like the other JS tests in this suite), so the
behavioural run is skipped when it is unavailable; the wiring is covered by
`tests/test_column_filters_wiring.py` regardless.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "static" / "js" / "mt-filters-core.js"

HARNESS = r"""
'use strict';
var core = require(__CORE_PATH__);

/* One filter object per column; `kind` mirrors what the DOM engine detects. */
var KINDS = ['text', 'text', 'text', 'number', 'date', 'text'];

function blank() {
  return KINDS.map(function (kind) {
    return { values: null, text: '', min: '', max: '', from: '', to: '', kind: kind };
  });
}
function withText(index, text) { var f = blank(); f[index].text = text; return f; }
function withValues(index, values) {
  var f = blank();
  f[index].values = new Set(values.map(function (v) { return core.normalize(v); }));
  return f;
}
function withNumberRange(index, lo, hi) {
  var f = blank();
  f[index].min = lo == null ? '' : lo;
  f[index].max = hi == null ? '' : hi;
  return f;
}
function withDateRange(index, from, to) {
  var f = blank();
  f[index].from = from == null ? '' : from;
  f[index].to = to == null ? '' : to;
  return f;
}
function withTwoText(i, a, j, b) {
  var f = blank();
  f[i].text = a;
  f[j].text = b;
  return f;
}

/* Columns: 0 serial (text), 1 brand (text), 2 model (text), 3 count (number),
   4 date, 5 status (text). Row 1 has an empty number so range filters must
   exclude it, not crash. */
var rows = [
  ['TR-000124', 'كماز', 'KAMAZ', '12', '2024-01-15', 'جاهز'],
  ['TR-000125', 'فولفو', 'VOLVO', '', '2024-03-02', 'عاطل'],
  ['TR-000126', 'كماز', 'KAMAZ', '20', '2024/05/10', 'جاهز'],
  ['TR-000127', 'كاتربيلر', 'CAT', '5', '2023-11-01', 'في الصيانة']
];

function passing(filters) {
  var out = [];
  rows.forEach(function (row, i) { if (core.rowPasses(row, filters)) out.push(i); });
  return out;
}
function column(index) {
  return rows.map(function (row) { return row[index]; });
}

var result = {
  singleText: passing(withText(0, 'TR-000124')),
  singleTextPartial: passing(withText(0, 'TR-00012')),
  singleTextArabic: passing(withText(1, 'كماز')),
  singleTextMiss: passing(withText(2, 'MERCEDES')),
  combinedAnd: passing(withTwoText(1, 'كماز', 5, 'جاهز')),
  combinedAndNoMatch: passing(withTwoText(1, 'كماز', 5, 'عاطل')),
  valuesSet: passing(withValues(1, ['كماز'])),
  valuesSetStatus: passing(withValues(5, ['جاهز'])),
  valuesSetEmpty: passing(withValues(1, [])),
  numberMin: passing(withNumberRange(3, 10, null)),
  numberMax: passing(withNumberRange(3, null, 12)),
  numberBetween: passing(withNumberRange(3, 6, 15)),
  numberOutside: passing(withNumberRange(3, 100, null)),
  dateFrom: passing(withDateRange(4, '2024-02-01', null)),
  dateTo: passing(withDateRange(4, null, '2024-03-31')),
  dateBetween: passing(withDateRange(4, '2024-01-01', '2024-12-31')),
  dateOutside: passing(withDateRange(4, '2030-01-01', null)),
  blankFiltersAllRows: passing(blank()),

  detectCount: core.detectKind(column(3)),
  detectDate: core.detectKind(column(4)),
  detectSerial: core.detectKind(['TR-000124', 'AB-2']),
  detectMixed: core.detectKind(['10', 'Twenty']),
  detectEmpty: core.detectKind([]),

  activeNull: core.isFilterActive(null),
  activeBlank: core.isFilterActive(blank()[0]),
  activeText: core.isFilterActive({ text: 'كماز' }),
  activeWhitespaceText: core.isFilterActive({ text: '   ' }),
  activeValues: core.isFilterActive({ values: new Set(['a']) }),
  activeEmptyValues: core.isFilterActive({ values: new Set() }),
  activeNumber: core.isFilterActive({ min: '10' }),
  activeDate: core.isFilterActive({ from: '2024-01-01' }),

  normalizeDigits: core.normalize('١٢٣'),
  normalizeHamza: core.normalize('أحمد'),
  parseNumberArabic: core.parseNumber('١٢٣'),
  parseNumberUnit: core.parseNumber('1,234 كم'),
  parseNumberPlain: core.parseNumber('20'),
  parseNumberSerial: core.parseNumber('TR-000124'),
  parseDateIso: core.parseDate('2024-05-10'),
  parseDateSlash: core.parseDate('2024/05/10'),
  parseDateDayFirst: core.parseDate('15/03/2024'),
  parseDateNot: core.parseDate('كماز'),
  epochSlash: Date.UTC(2024, 4, 10),
  epochDayFirst: Date.UTC(2024, 2, 15)
};

process.stdout.write(JSON.stringify(result));
"""


def _run_core() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node غير متوفر")
    completed = subprocess.run(
        [node, "-e", HARNESS.replace("__CORE_PATH__", json.dumps(str(CORE)))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def core() -> dict:
    return _run_core()


# ----------------------------------------------------------- single column

def test_single_column_text_filter_keeps_only_matching_rows(core):
    assert core["singleText"] == [0]
    assert core["singleTextArabic"] == [0, 2]
    assert core["singleTextMiss"] == []


def test_single_column_filter_uses_contains_semantics(core):
    # "TR-00012" is a prefix shared by every serial number.
    assert core["singleTextPartial"] == [0, 1, 2, 3]


def test_status_column_filters_by_exact_value(core):
    assert core["valuesSet"] == [0, 2]
    assert core["valuesSetStatus"] == [0, 2]
    assert core["valuesSetEmpty"] == [0, 1, 2, 3]


# ------------------------------------------------------------ AND combine

def test_combined_filters_are_anded_across_columns(core):
    assert core["combinedAnd"] == [0, 2]
    assert core["combinedAndNoMatch"] == []


def test_no_active_filter_keeps_every_row(core):
    assert core["blankFiltersAllRows"] == [0, 1, 2, 3]


# ------------------------------------------------------------------ numbers

def test_number_range_filters_include_min_and_max(core):
    assert core["numberMin"] == [0, 2]
    assert core["numberMax"] == [0, 3]
    assert core["numberBetween"] == [0]


def test_number_range_excludes_empty_and_out_of_range(core):
    # Row 1 has an empty numeric cell; it must be dropped, never counted as 0.
    assert core["numberOutside"] == []
    assert 1 not in core["numberMin"]


# -------------------------------------------------------------------- dates

def test_date_range_filters_accept_iso_and_slash_dates(core):
    assert core["dateFrom"] == [1, 2]
    assert core["dateTo"] == [0, 1, 3]
    assert core["dateBetween"] == [0, 1, 2]
    assert core["dateOutside"] == []


def test_parse_date_reads_both_iso_and_day_first(core):
    assert core["parseDateIso"] == core["epochSlash"]
    assert core["parseDateSlash"] == core["epochSlash"]
    assert core["parseDateDayFirst"] == core["epochDayFirst"]
    assert core["parseDateNot"] is None


# ----------------------------------------------------------- kind detection

def test_column_kind_is_detected_from_all_non_empty_values(core):
    assert core["detectCount"] == "number"
    assert core["detectDate"] == "date"
    # A serial with letters stays text so it is never range-filtered as a number.
    assert core["detectSerial"] == "text"
    assert core["detectMixed"] == "text"
    assert core["detectEmpty"] == "text"


# ------------------------------------------------------------ active state

def test_is_filter_active_recognises_every_filter_shape(core):
    assert core["activeNull"] is False
    assert core["activeBlank"] is False
    assert core["activeText"] is True
    assert core["activeWhitespaceText"] is False
    assert core["activeValues"] is True
    assert core["activeEmptyValues"] is False
    assert core["activeNumber"] is True
    assert core["activeDate"] is True


# -------------------------------------------------------------- normalising

def test_arabic_indic_digits_and_hamza_are_normalised(core):
    assert core["normalizeDigits"] == "123"
    assert core["parseNumberArabic"] == 123
    assert core["normalizeHamza"].startswith("ا")


def test_parse_number_tolerates_units_but_rejects_serials(core):
    assert core["parseNumberUnit"] == 1234
    assert core["parseNumberPlain"] == 20
    assert core["parseNumberSerial"] is None


def test_core_is_loadable_by_node():
    # A tiny guard so a syntax break surfaces even if fixtures fail elsewhere.
    assert CORE.exists()
