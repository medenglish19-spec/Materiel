(function () {
  'use strict';

  const key = 'materiel:data-version:v1';
  const readVersion = () => {
    try { return Number(localStorage.getItem(key) || 0); }
    catch (_) { return 0; }
  };
  const markChanged = () => {
    try { localStorage.setItem(key, String(readVersion() + 1)); }
    catch (_) { /* Storage may be disabled; normal navigation still refreshes pages. */ }
  };

  let pageVersion = readVersion();
  let refreshing = false;
  const refreshIfStale = () => {
    if (refreshing || readVersion() === pageVersion) return;
    refreshing = true;
    window.location.reload();
  };

  window.addEventListener('pageshow', refreshIfStale);
  window.addEventListener('storage', event => {
    if (event.key === key) refreshIfStale();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshIfStale();
  });

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes((form.method || 'get').toUpperCase())) return;
    markChanged();
  }, true);

  const nativeFetch = window.fetch;
  window.fetch = async function (...args) {
    const request = args[0];
    const options = args[1] || {};
    const method = String(options.method || request?.method || 'GET').toUpperCase();
    let sameOrigin = false;
    try {
      sameOrigin = new URL(typeof request === 'string' ? request : request.url, window.location.href).origin === window.location.origin;
    } catch (_) { /* Ignore malformed or unsupported request inputs. */ }
    const response = await nativeFetch.apply(this, args);
    if (sameOrigin && response.ok && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) markChanged();
    return response;
  };
})();
