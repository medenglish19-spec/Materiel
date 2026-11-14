/*
 * Double-submit CSRF support.
 *
 * The server sets a readable `csrf_token` cookie and renders the same value in
 * a <meta name="csrf-token"> tag.  This script copies it into:
 *   - every non-GET HTML form (hidden field), and
 *   - same-origin fetch()/XHR requests with an unsafe method (header).
 *
 * It is intentionally dependency-free and runs before other page scripts.
 */
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? (meta.getAttribute("content") || "") : "";
  if (!token) return;

  var UNSAFE = { POST: true, PUT: true, PATCH: true, DELETE: true };

  function isUnsafeForm(form) {
    var method = (form.getAttribute("method") || "get").toLowerCase();
    return method !== "get";
  }

  function addFormToken(form) {
    if (!form || !isUnsafeForm(form)) return;
    var input = form.querySelector('input[name="csrf_token"]');
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = "csrf_token";
      form.appendChild(input);
    }
    input.value = token;
  }

  function scan(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var forms = scope.querySelectorAll ? scope.querySelectorAll("form") : [];
    for (var i = 0; i < forms.length; i += 1) addFormToken(forms[i]);
  }

  // Capture phase catches forms even when another handler calls preventDefault.
  document.addEventListener(
    "submit",
    function (event) {
      addFormToken(event.target);
    },
    true
  );

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scan(document);
    });
  } else {
    scan(document);
  }

  // Pages build forms and rows dynamically; cover those too.
  if (window.MutationObserver) {
    new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i += 1) {
        var added = mutations[i].addedNodes;
        for (var j = 0; j < added.length; j += 1) {
          var node = added[j];
          if (node.nodeType !== 1) continue;
          if (node.tagName === "FORM") addFormToken(node);
          else scan(node);
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (error) {
      return false;
    }
  }

  function withHeader(headers) {
    var result = new Headers(headers || undefined);
    if (!result.has("X-CSRF-Token")) result.set("X-CSRF-Token", token);
    return result;
  }

  var originalFetch = window.fetch;
  if (originalFetch) {
    window.fetch = function (input, init) {
      var options = init ? Object.assign({}, init) : {};
      var method;
      var url;
      if (typeof Request !== "undefined" && input instanceof Request) {
        method = options.method || input.method || "GET";
        url = input.url;
      } else {
        method = options.method || "GET";
        url = typeof input === "string" ? input : (input && input.url) || "";
      }
      if (UNSAFE[String(method).toUpperCase()] && sameOrigin(url)) {
        if (typeof Request !== "undefined" && input instanceof Request) {
          options.headers = withHeader(options.headers || input.headers);
          input = new Request(input, options);
          return originalFetch.call(this, input);
        }
        options.headers = withHeader(options.headers);
        return originalFetch.call(this, input, options);
      }
      return originalFetch.apply(this, arguments);
    };
  }

  var originalOpen = XMLHttpRequest.prototype.open;
  var originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__csrfUnsafe = UNSAFE[String(method).toUpperCase()] && sameOrigin(url);
    return originalOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    if (this.__csrfUnsafe) {
      try {
        this.setRequestHeader("X-CSRF-Token", token);
      } catch (error) {
        /* header can no longer be set; let the server reject the request */
      }
    }
    return originalSend.apply(this, arguments);
  };
})();
