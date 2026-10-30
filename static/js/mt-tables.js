/* ============================================================================
   Materiel — shared table behaviour.
   Companion to /static/css/mt-tables.css.

   1. Fits every `[data-mt-region]` scroll region to the space that is actually
      available on screen, so tall tables scroll instead of stretching the page.
   2. Provides one reusable row-actions menu (`MaterielTables.openRowMenu`) so
      pages do not ship their own copy of the same behaviour:
        · opens from a ⋮ trigger or a right-click;
        · never runs an action merely by opening;
        · closes on outside click, Escape or any scroll;
        · full keyboard navigation (arrows / Home / End / Escape / Tab).
   It is intentionally additive: it does not touch existing handlers and it is
   idempotent, so it can safely run more than once.
   ========================================================================== */
(function () {
  'use strict';

  var GAP = 16;
  var MIN = 180;

  /* ------------------------------------------------------------------ fit */
  function fitRegion(region) {
    var rect = region.getBoundingClientRect();
    if (rect.bottom <= 0 || rect.top >= window.innerHeight - GAP) {
      region.style.removeProperty('--mt-region-max-height');
    } else {
      /* Keep the region within the visible viewport as its top scrolls away. */
      var available = Math.floor(window.innerHeight - Math.max(0, rect.top) - GAP);
      if (available >= MIN) {
        region.style.setProperty('--mt-region-max-height', available + 'px');
      } else {
        region.style.removeProperty('--mt-region-max-height');
      }
    }
  }

  function fitAll() {
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-mt-region]'),
      fitRegion
    );
  }

  var scheduled = false;
  function scheduleFit() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () {
      scheduled = false;
      fitAll();
    });
  }

  /* Regions inside hidden tabs report a zero box, so their fitted height would
     go stale once the tab is shown. Observing the region refits it the moment
     it gets a real size again (the rAF in scheduleFit prevents a resize loop). */
  var resizeObserver = null;
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(function () { scheduleFit(); });
  }

  function prepareRegion(region) {
    if (region.getAttribute('data-mt-region-ready')) return;
    region.setAttribute('data-mt-region-ready', '1');
    if (!region.hasAttribute('tabindex')) region.setAttribute('tabindex', '0');
    if (!region.hasAttribute('role')) region.setAttribute('role', 'region');
    if (!region.getAttribute('aria-label')) {
      region.setAttribute('aria-label', 'جدول البيانات');
    }
    if (resizeObserver) resizeObserver.observe(region);
  }

  function initRegions() {
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-mt-region]'),
      prepareRegion
    );
    fitAll();
  }

  /* ------------------------------------------------------------- row menu */
  var openMenu = null;
  var activeTrigger = null;

  function closeRowMenu() {
    if (activeTrigger) {
      activeTrigger.setAttribute('aria-expanded', 'false');
      activeTrigger = null;
    }
    if (openMenu) {
      openMenu.remove();
      openMenu = null;
    }
  }

  function openRowMenu(options) {
    options = options || {};
    closeRowMenu();

    var trigger = options.trigger || null;
    var items = options.items || [];
    if (!items.length) return null;

    var menu = document.createElement('div');
    menu.className = 'mt-row-menu';
    menu.setAttribute('role', 'menu');

    var buttons = [];
    items.forEach(function (item) {
      var button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('role', 'menuitem');
      button.className = 'mt-row-menu-item' + (item.danger ? ' danger' : '');
      if (item.disabled) button.disabled = true;
      button.textContent = item.label;
      button.addEventListener('click', function (event) {
        event.stopPropagation();
        closeRowMenu();
        if (typeof item.onSelect === 'function') item.onSelect();
      });
      buttons.push(button);
      menu.appendChild(button);
    });

    document.body.appendChild(menu);

    var anchorX;
    var anchorY;
    if (trigger) {
      var rect = trigger.getBoundingClientRect();
      anchorX = rect.left + rect.width / 2;
      anchorY = rect.bottom + 4;
    } else {
      anchorX = options.x || 0;
      anchorY = options.y || 0;
    }

    var menuWidth = menu.offsetWidth;
    var menuHeight = menu.offsetHeight;
    var left = Math.max(8, Math.min(anchorX - menuWidth / 2, window.innerWidth - menuWidth - 8));
    var top = Math.max(8, Math.min(anchorY, window.innerHeight - menuHeight - 8));
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';

    openMenu = menu;
    activeTrigger = trigger;
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
    if (buttons[0]) buttons[0].focus();

    var focusIndex = 0;
    function move(step) {
      focusIndex = (focusIndex + step + buttons.length) % buttons.length;
      buttons[focusIndex].focus();
    }

    menu.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
      else if (event.key === 'Home') { event.preventDefault(); focusIndex = 0; buttons[0].focus(); }
      else if (event.key === 'End') { event.preventDefault(); focusIndex = buttons.length - 1; buttons[buttons.length - 1].focus(); }
      else if (event.key === 'Tab') { closeRowMenu(); }
    });

    return menu;
  }

  function isMenuOpen() {
    return !!openMenu;
  }

  /* Outside click, Escape and scroll all dismiss an open menu. Capture phase
     and stopImmediatePropagation keep the shared Escape handler from also
     treating the keystroke as "exit the page editor". */
  document.addEventListener('click', function (event) {
    if (openMenu && !openMenu.contains(event.target) &&
        !(activeTrigger && activeTrigger.contains(event.target))) {
      closeRowMenu();
    }
  }, true);

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape' || !openMenu) return;
    var trigger = activeTrigger;
    event.preventDefault();
    event.stopImmediatePropagation();
    closeRowMenu();
    if (trigger && typeof trigger.focus === 'function') trigger.focus();
  }, true);

  document.addEventListener('scroll', function () {
    if (openMenu) closeRowMenu();
  }, true);

  window.addEventListener('resize', function () {
    scheduleFit();
    if (openMenu) closeRowMenu();
  });
  window.addEventListener('scroll', scheduleFit, { passive: true });

  /* ------------------------------------------------------------------------
     Per-column filters.

     Every list table lives inside a `[data-mt-region]` wrapper, so the shared
     engine enhances each region's table automatically: it derives the filter
     kind of every meaningful column from the real rows and adds a small ▼
     trigger in that column's header. Columns are combined with AND, while the
     distinct values checked inside one column are OR-ed.

     It is intentionally conservative:
       · action / selection columns (kind `mt-actions-th`, empty headers, links
         only, checkboxes) get no filter;
       · data-entry tables (rows containing inputs) and hierarchical tables
         (rows carrying `data-level`) are left completely alone;
       · a table that already ships its own filters (`.col-filter`, e.g. the
         maintenance operation library) is skipped;
       · `data-mt-no-filter` on the table or any ancestor disables it.

     Hiding a row uses a class (`.mt-col-hidden`) rather than an inline
     `display`, so it composes with each page's existing search / pagination:
     a row must satisfy BOTH the page's own visibility and the column filters.
     ---------------------------------------------------------------------- */
  var CORE = window.MaterielFilterCore;

  var FILTER_SKIP_HEADERS = {};
  ['#', '—', '-', 'الاجراءات', 'اجراء', 'الاجراء', 'العمليات', 'عمليه', 'عمليات',
    'السجل', 'تفاصيل', 'التفاصيل', 'عرض', 'فتح', 'فتح السجل', 'تحرير', 'تعديل',
    'اختيار', 'تحديد', 'action', 'actions'].forEach(function (h) {
    FILTER_SKIP_HEADERS[h] = true;
  });

  var openFilterMenuEl = null;
  var activeFilterTrigger = null;

  function headerRow(table) {
    if (table.tHead && table.tHead.rows.length) return table.tHead.rows[0];
    var firstBody = table.tBodies[0];
    if (firstBody && firstBody.rows.length && firstBody.rows[0].querySelector('th')) {
      return firstBody.rows[0];
    }
    return null;
  }

  function headerCells(table) {
    var row = headerRow(table);
    return row ? Array.prototype.slice.call(row.cells) : [];
  }

  function isMessageRow(row, colCount) {
    return row.cells.length === 1 && (row.cells[0].colSpan || 1) >= colCount;
  }

  function dataRows(table, headRow) {
    var rows = [];
    Array.prototype.forEach.call(table.tBodies, function (body) {
      Array.prototype.forEach.call(body.rows, function (row) {
        if (row === headRow) return;
        if (row.querySelector('th')) return;
        if (row.hasAttribute('data-mt-filter-auxiliary')) return;
        rows.push(row);
      });
    });
    return rows;
  }

  function columnSamples(table, rows, index, colCount) {
    var samples = [];
    rows.forEach(function (row) {
      if (isMessageRow(row, colCount)) return;
      var cell = row.cells[index];
      if (cell) samples.push((cell.textContent || '').trim());
    });
    return samples;
  }

  function looksLikeLinkColumn(rows, index, colCount) {
    var total = 0, links = 0;
    rows.forEach(function (row) {
      if (isMessageRow(row, colCount)) return;
      var cell = row.cells[index];
      if (!cell) return;
      total++;
      if (cell.querySelector('a,button:not(.row-action-toggle):not([data-menu-action])')) links++;
    });
    return total > 0 && links / total > 0.6;
  }

  function buildColumns(table) {
    var core = CORE;
    var cells = headerCells(table);
    if (cells.length < 2) return null;
    var i;
    for (i = 0; i < cells.length; i++) {
      if ((cells[i].colSpan || 1) > 1) return null;   /* grouped header */
    }
    var rows = dataRows(table, headerRow(table));
    var columns = [];
    for (i = 0; i < cells.length; i++) {
      var th = cells[i];
      var label = (th.textContent || '').trim();
      if (th.hasAttribute('data-mt-no-filter')) continue;
      if (th.querySelector('input[type=checkbox],input[type=radio]')) continue;
      if (!label) continue;
      if (FILTER_SKIP_HEADERS[core.normalize(label)]) continue;
      var forceFilter = th.hasAttribute('data-mt-force-filter');
      if (!forceFilter && looksLikeLinkColumn(rows, i, cells.length)) continue;
      var samples = columnSamples(table, rows, i, cells.length);
      var hasValue = samples.some(function (s) { return s !== ''; });
      if (!hasValue && !forceFilter) continue;
      columns.push({
        index: i,
        th: th,
        btn: null,
        kind: core.detectKind(samples),
        filter: { values: null, text: '', min: '', max: '', from: '', to: '' }
      });
    }
    return columns.length ? columns : null;
  }

  function isEditorTable(table) {
    return !!table.querySelector('tbody input:not([type="checkbox"]):not([type="radio"]), tbody select, tbody textarea');
  }

  function isHierarchicalTable(table) {
    return !!table.querySelector('tbody tr[data-level]');
  }

  function removeFilterButtons(table) {
    if (table.__mtColumns) {
      table.__mtColumns.forEach(function (col) {
        if (col.btn && col.btn.parentNode) col.btn.parentNode.removeChild(col.btn);
      });
    }
    table.__mtColumns = null;
    table.removeAttribute('data-mt-filters-ready');
  }

  function enhanceTable(table) {
    if (!CORE || !table || table.getAttribute('data-mt-filters-off')) return;
    if (table.getAttribute('data-mt-filters-ready')) return;
    if (table.closest('[data-mt-no-filter]')) return;
    if (table.hasAttribute('data-mt-no-filter')) return;
    if (table.querySelector('.col-filter')) return;      /* page ships its own */
    if (isEditorTable(table) || isHierarchicalTable(table)) return;
    var columns = buildColumns(table);
    if (!columns) return;
    columns.forEach(function (col) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mt-col-filter';
      btn.textContent = '▼';
      btn.setAttribute('aria-label', 'تصفية العمود');
      btn.title = 'تصفية';
      btn.addEventListener('click', function (event) {
        event.stopPropagation();
        openFilterMenu(table, col, btn);
      });
      col.th.appendChild(btn);
      col.btn = btn;
    });
    table.__mtColumns = columns;
    table.setAttribute('data-mt-filters-ready', '1');
    applyTableFilters(table);
  }

  function unenhanceTable(table) {
    removeFilterButtons(table);
    table.setAttribute('data-mt-filters-off', '1');
    var rows = dataRows(table, headerRow(table));
    rows.forEach(function (row) { row.classList.remove('mt-col-hidden'); });
  }

  function applyTableFilters(table) {
    var columns = table.__mtColumns;
    if (!columns) return;
    var cells = headerCells(table);
    var colCount = cells.length;
    columns.forEach(function (col) {
      var active = CORE.isFilterActive(col.filter);
      if (col.btn) {
        col.btn.classList.toggle('active', active);
        col.btn.textContent = active ? '▼•' : '▼';
      }
    });
    var rows = dataRows(table, headerRow(table));
    rows.forEach(function (row) {
      if (isMessageRow(row, colCount)) {
        row.classList.remove('mt-col-hidden');
        return;
      }
      var ok = true;
      for (var i = 0; i < columns.length; i++) {
        var col = columns[i];
        if (!CORE.isFilterActive(col.filter)) continue;
        var cell = row.cells[col.index];
        if (!CORE.matchesCell(cell ? cell.textContent : '', col.filter, col.kind)) {
          ok = false;
          break;
        }
      }
      row.classList.toggle('mt-col-hidden', !ok);
    });
    syncFilterEmptyState(table, columns, rows, colCount);
    if (typeof CustomEvent === 'function') {
      table.dispatchEvent(new CustomEvent('mt:filters-applied', { bubbles: true }));
    }
  }

  function syncFilterEmptyState(table, columns, rows, colCount) {
    var body = table.tBodies[0];
    if (!body) return;
    var emptyRow = body.querySelector('tr[data-mt-filter-auxiliary="filter-empty"]');
    var records = rows.filter(function (row) { return !isMessageRow(row, colCount); });
    var active = columns.some(function (column) { return CORE.isFilterActive(column.filter); });
    var visible = records.some(function (row) {
      return !row.hidden && !row.classList.contains('mt-col-hidden') &&
        window.getComputedStyle(row).getPropertyValue('display') !== 'none';
    });
    if (!active || !records.length || visible) {
      if (emptyRow) emptyRow.remove();
      return;
    }
    if (!emptyRow) {
      emptyRow = document.createElement('tr');
      emptyRow.setAttribute('data-mt-filter-auxiliary', 'filter-empty');
      var cell = document.createElement('td');
      cell.colSpan = Math.max(1, colCount);
      var message = document.createElement('div');
      message.className = 'mt-filter-empty-state';
      message.setAttribute('role', 'status');
      var text = document.createElement('span');
      text.textContent = 'لا توجد نتائج تطابق عوامل التصفية الحالية.';
      var clear = document.createElement('button');
      clear.type = 'button';
      clear.className = 'mt-filter-clear';
      clear.textContent = 'مسح التصفية';
      clear.addEventListener('click', function () {
        columns.forEach(function (column) {
          column.filter = { values: null, text: '', min: '', max: '', from: '', to: '' };
        });
        applyTableFilters(table);
      });
      message.appendChild(text);
      message.appendChild(clear);
      cell.appendChild(message);
      emptyRow.appendChild(cell);
      body.appendChild(emptyRow);
    }
    if (emptyRow.cells[0]) emptyRow.cells[0].colSpan = Math.max(1, colCount);
  }

  function closeFilterMenu() {
    if (openFilterMenuEl) {
      openFilterMenuEl.remove();
      openFilterMenuEl = null;
    }
    if (activeFilterTrigger) {
      activeFilterTrigger.setAttribute('aria-expanded', 'false');
      activeFilterTrigger = null;
    }
  }

  function distinctValues(table, col) {
    var cells = headerCells(table);
    var rows = dataRows(table, headerRow(table));
    var seen = {};
    var out = [];
    rows.forEach(function (row) {
      if (isMessageRow(row, cells.length)) return;
      var cell = row.cells[col.index];
      var text = cell ? (cell.textContent || '').trim() : '';
      if (text === '') return;
      var key = CORE.normalize(text);
      if (seen[key]) return;
      seen[key] = true;
      out.push({ value: text, key: key });
    });
    out.sort(function (a, b) { return a.value.localeCompare(b.value, 'ar'); });
    return out;
  }

  function openFilterMenu(table, col, trigger) {
    closeFilterMenu();
    var values = distinctValues(table, col);
    var filter = col.filter;

    var menu = document.createElement('div');
    menu.className = 'mt-filter-menu';
    menu.setAttribute('role', 'dialog');
    menu.setAttribute('dir', 'rtl');

    var title = document.createElement('div');
    title.className = 'mt-filter-title';
    title.textContent = 'تصفية: ' + (col.th.textContent || '').replace(/[▼•]/g, '').trim();
    menu.appendChild(title);

    var search = document.createElement('input');
    search.type = 'search';
    search.className = 'mt-filter-search';
    search.placeholder = 'بحث في القيم...';
    search.setAttribute('aria-label', 'بحث في القيم');
    menu.appendChild(search);

    var actions = document.createElement('div');
    actions.className = 'mt-filter-actions';
    actions.innerHTML = '<button type="button" data-select-all>تحديد الكل</button>' +
      '<button type="button" data-clear>مسح</button>' +
      '<button type="button" data-apply>تطبيق</button>';
    menu.appendChild(actions);

    var contains = null;
    if (col.kind === 'text') {
      contains = document.createElement('input');
      contains.type = 'search';
      contains.className = 'mt-filter-contains';
      contains.placeholder = 'يحتوي على...';
      contains.value = filter.text || '';
      menu.appendChild(contains);
    }

    var minInput = null, maxInput = null, fromInput = null, toInput = null;
    if (col.kind === 'number' || col.kind === 'date') {
      var range = document.createElement('div');
      range.className = 'mt-filter-range';
      if (col.kind === 'number') {
        minInput = document.createElement('input');
        minInput.type = 'number';
        minInput.placeholder = 'من';
        minInput.value = filter.min || '';
        maxInput = document.createElement('input');
        maxInput.type = 'number';
        maxInput.placeholder = 'إلى';
        maxInput.value = filter.max || '';
      } else {
        fromInput = document.createElement('input');
        fromInput.type = 'date';
        fromInput.title = 'من تاريخ';
        fromInput.value = filter.from || '';
        toInput = document.createElement('input');
        toInput.type = 'date';
        toInput.title = 'إلى تاريخ';
        toInput.value = filter.to || '';
      }
      range.appendChild(col.kind === 'number' ? minInput : fromInput);
      range.appendChild(col.kind === 'number' ? maxInput : toInput);
      menu.appendChild(range);
    }

    var valuesBox = document.createElement('div');
    valuesBox.className = 'mt-filter-values';
    menu.appendChild(valuesBox);

    function drawValues(term) {
      var t = CORE.normalize(term || '');
      valuesBox.innerHTML = '';
      values.forEach(function (item) {
        if (t && item.key.indexOf(t) === -1) return;
        var label = document.createElement('label');
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = item.value;
        cb.dataset.key = item.key;
        cb.checked = (!filter.values || !filter.values.size) ? true : filter.values.has(item.key);
        label.appendChild(cb);
        label.appendChild(document.createTextNode(item.value));
        valuesBox.appendChild(label);
      });
    }
    drawValues('');

    document.body.appendChild(menu);
    var rect = trigger.getBoundingClientRect();
    menu.style.top = Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - menu.offsetHeight - 8)) + 'px';
    menu.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8)) + 'px';

    search.addEventListener('input', function () { drawValues(search.value); });
    actions.querySelector('[data-select-all]').addEventListener('click', function () {
      Array.prototype.forEach.call(valuesBox.querySelectorAll('input'), function (cb) { cb.checked = true; });
    });
    actions.querySelector('[data-clear]').addEventListener('click', function () {
      Array.prototype.forEach.call(valuesBox.querySelectorAll('input'), function (cb) { cb.checked = false; });
    });
    actions.querySelector('[data-apply]').addEventListener('click', function () {
      var checked = Array.prototype.slice.call(valuesBox.querySelectorAll('input:checked'));
      filter.values = (checked.length === values.length)
        ? null
        : new Set(checked.map(function (cb) { return cb.dataset.key; }));
      if (contains) filter.text = contains.value || '';
      if (minInput) filter.min = minInput.value;
      if (maxInput) filter.max = maxInput.value;
      if (fromInput) filter.from = fromInput.value;
      if (toInput) filter.to = toInput.value;
      closeFilterMenu();
      applyTableFilters(table);
    });

    openFilterMenuEl = menu;
    activeFilterTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    search.focus();
  }

  document.addEventListener('click', function (event) {
    if (openFilterMenuEl && !openFilterMenuEl.contains(event.target) &&
        !(event.target.closest && event.target.closest('.mt-col-filter'))) {
      closeFilterMenu();
    }
  }, true);

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape' || !openFilterMenuEl) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    closeFilterMenu();
  }, true);

  document.addEventListener('scroll', function () {
    if (openFilterMenuEl) closeFilterMenu();
  }, true);

  function enhanceAll() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-mt-region]'), function (region) {
      var table = region.querySelector('table');
      if (table) enhanceTable(table);
    });
    Array.prototype.forEach.call(document.querySelectorAll('table[data-mt-filters]'), function (table) {
      if (table.getAttribute('data-mt-filters') !== 'off') enhanceTable(table);
    });
    Array.prototype.forEach.call(document.querySelectorAll('table[data-mt-filters-ready]'), function (table) {
      if (isEditorTable(table) || isHierarchicalTable(table)) unenhanceTable(table);
    });
    Array.prototype.forEach.call(document.querySelectorAll('table[data-mt-filters-ready]'), function (table) {
      applyTableFilters(table);
    });
    /* also enhance eligible tables outside [data-mt-region],
       using the same skip rules so they compose cleanly with page-level
       search/pagination/sort and do not duplicate filters already present. */
    Array.prototype.forEach.call(document.querySelectorAll('table:not([data-mt-region])'), function (table) {
      if (table.getAttribute('data-mt-filters-ready')) return;
      if (table.closest('[data-mt-no-filter]') || table.hasAttribute('data-mt-no-filter')) return;
      if (table.querySelector('.col-filter')) return;
      if (table.querySelector('tbody input, tbody select, tbody textarea')) return;
      if (table.querySelector('tr[data-level]')) return;
      var grouped = false;
      table.querySelectorAll('thead th').forEach(function (th) {
        if ((th.colSpan || 1) > 1) { grouped = true; return false; }
      });
      if (grouped) return;
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var hasData = false;
      Array.prototype.forEach.call(tbody.rows, function (row) {
        if (row.cells.length <= 1) return;
        if (row.cells[0].textContent.trim()) { hasData = true; }
      });
      if (!hasData) return;
      enhanceTable(table);
    });
  }

  var filtersScheduled = false;
  function scheduleFilterRefresh() {
    if (filtersScheduled) return;
    filtersScheduled = true;
    window.requestAnimationFrame(function () {
      filtersScheduled = false;
      enhanceAll();
    });
  }

  function initColumnFilters() {
    enhanceAll();
    if (typeof MutationObserver !== 'undefined') {
      new MutationObserver(function () { scheduleFilterRefresh(); })
        .observe(document.body, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initRegions();
      initColumnFilters();
    });
  } else {
    initRegions();
    initColumnFilters();
  }

  window.MaterielTables = {
    openRowMenu: openRowMenu,
    closeRowMenu: closeRowMenu,
    isMenuOpen: isMenuOpen,
    refresh: function () { initRegions(); enhanceAll(); },
    refreshFilters: function () { enhanceAll(); },
    closeFilterMenu: closeFilterMenu
  };
})();
