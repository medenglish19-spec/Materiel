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
    /* Only measurements taken while the region is on screen are meaningful. */
    if (rect.top >= 0 && rect.top < window.innerHeight * 0.85) {
      var available = Math.floor(window.innerHeight - rect.top - GAP);
      if (available >= MIN) {
        region.style.setProperty('--mt-region-max-height', available + 'px');
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initRegions);
  } else {
    initRegions();
  }

  window.MaterielTables = {
    openRowMenu: openRowMenu,
    closeRowMenu: closeRowMenu,
    isMenuOpen: isMenuOpen,
    refresh: function () { initRegions(); }
  };
})();
