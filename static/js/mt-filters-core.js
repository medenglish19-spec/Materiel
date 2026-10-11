/* ============================================================================
   Materiel — per-column table filter core (pure, DOM-free).

   This file holds ONLY the matching logic used by the shared column filters:
   text normalisation, number/date parsing, column-kind detection and the
   single-cell / whole-row predicate. It deliberately touches no DOM so it can
   be unit-tested in isolation (browser: `window.MaterielFilterCore`, Node:
   `require(...)`). The DOM wiring lives in /static/js/mt-tables.js.

   Filtering semantics: every active column filter must pass for a row to stay
   visible (AND across columns). Values inside one column are OR-ed when the
   user checks several distinct values.
   ========================================================================== */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MaterielFilterCore = api;
})(typeof window !== 'undefined' ? window
  : (typeof globalThis !== 'undefined' ? globalThis : null), function () {
  'use strict';

  var ARABIC_DIGITS = {
    '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
    '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
    '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
    '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'
  };

  /* Normalise a value for comparison: Arabic-Indic digits → ASCII, drop
     diacritics/tatweel, fold hamza/alef and taa-marbuta, collapse spaces,
     lowercase. Pure and locale-independent. */
  function normalize(value) {
    var s = String(value == null ? '' : value);
    s = s.replace(/[٠-٩۰-۹]/g, function (d) { return ARABIC_DIGITS[d] || d; });
    s = s.replace(/[\u064B-\u065F\u0670\u0640]/g, '');
    s = s.replace(/[أإآٱ]/g, 'ا').replace(/ى/g, 'ي').replace(/ة/g, 'ه');
    s = s.replace(/\s+/g, ' ').trim().toLowerCase();
    return s;
  }

  /* Parse a numeric cell, tolerating thousands separators, a leading sign and
     a trailing unit word (كم / ساعة / يوم / لتر / %). Returns null when the
     cell is not a plain number — so serial numbers such as "TR-000124" stay
     text and are never mis-detected as numeric. */
  function parseNumber(value) {
    var s = normalize(value);
    if (!s) return null;
    s = s.replace(/(كم|كيلومتر|كلم|ساعه|ساعات|يوم|ايام|لتر|%)/g, '').trim();
    s = s.replace(/[,\s]/g, '');
    if (!/^[+\-]?\d+(\.\d+)?$/.test(s)) return null;
    var n = Number(s);
    return isNaN(n) ? null : n;
  }

  /* Parse a date cell to a UTC timestamp in ms. Accepts ISO (YYYY-MM-DD),
     day-first (DD/MM/YYYY, the convention the app renders) and YYYY/MM/DD.
     Returns null when the cell is not a date. */
  function parseDate(value) {
    var s = normalize(value);
    if (!s) return null;
    var m;
    if ((m = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/.exec(s))) {
      return Date.UTC(+m[1], +m[2] - 1, +m[3]);
    }
    if ((m = /^(\d{1,2})[-/](\d{1,2})[-/](\d{4})/.exec(s))) {
      return Date.UTC(+m[3], +m[2] - 1, +m[1]);
    }
    return null;
  }

  /* Decide how a column should be filtered from its sample values. A column is
     numeric/date only when EVERY non-empty value parses as such; otherwise it
     is treated as text (exact-value selection + "contains"). */
  function detectKind(values) {
    var items = (values || []).map(normalize).filter(function (v) { return v !== ''; });
    if (!items.length) return 'text';
    var numbers = 0, dates = 0;
    items.forEach(function (v) {
      if (parseNumber(v) !== null) numbers++;
      if (parseDate(v) !== null) dates++;
    });
    if (numbers === items.length) return 'number';
    if (dates === items.length) return 'date';
    return 'text';
  }

  function hasRange(v) {
    return v !== undefined && v !== null && String(v).trim() !== '';
  }

  /* True when a single cell value passes one column's filter. `filter` is
     { values: Set<string>|null, text: string, min, max, from, to }. An empty
     or absent part imposes no restriction. */
  function matchesCell(value, filter, kind) {
    if (!filter) return true;
    var n = normalize(value);
    if (filter.values && filter.values.size && !filter.values.has(n)) return false;
    if (filter.text) {
      var q = normalize(filter.text);
      if (q && n.indexOf(q) === -1) return false;
    }
    if (kind === 'number' && (hasRange(filter.min) || hasRange(filter.max))) {
      var num = parseNumber(value);
      if (num === null) return false;
      if (hasRange(filter.min) && num < Number(normalize(filter.min))) return false;
      if (hasRange(filter.max) && num > Number(normalize(filter.max))) return false;
    }
    if (kind === 'date' && (hasRange(filter.from) || hasRange(filter.to))) {
      var t = parseDate(value);
      if (t === null) return false;
      if (hasRange(filter.from) && t < parseDate(filter.from)) return false;
      if (hasRange(filter.to) && t > parseDate(filter.to)) return false;
    }
    return true;
  }

  /* AND across columns: `values[i]` is the cell text of column i. */
  function rowPasses(values, filters) {
    for (var i = 0; i < filters.length; i++) {
      var f = filters[i];
      if (!matchesCell(values[i], f, f && f.kind)) return false;
    }
    return true;
  }

  function isFilterActive(filter) {
    if (!filter) return false;
    if (filter.values && filter.values.size) return true;
    if (filter.text && normalize(filter.text)) return true;
    return hasRange(filter.min) || hasRange(filter.max) ||
      hasRange(filter.from) || hasRange(filter.to);
  }

  return {
    normalize: normalize,
    parseNumber: parseNumber,
    parseDate: parseDate,
    detectKind: detectKind,
    matchesCell: matchesCell,
    rowPasses: rowPasses,
    isFilterActive: isFilterActive
  };
});
