"""Cross-site request forgery protection for cookie-authenticated requests.

The application authenticates browsers with a SameSite=Lax session cookie.
That already blocks most cross-site POSTs, but it is not a complete defence
(older browsers, same-site subdomains and some navigation flows).  This module
adds the standard double-submit pattern:

* the server issues a random ``csrf_token`` cookie that JavaScript can read;
* every unsafe request made with a session cookie must echo the same value in
  the ``X-CSRF-Token`` header or the ``csrf_token`` form field;
* the token does not need server-side storage, so no schema or shared cache is
  involved.

Requests without a session cookie are not cookie-authenticated, so they are
left to the normal authentication dependency (which answers 401).  The public
``/login`` and ``/setup`` forms are exempt because they run before a session
exists.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.core.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_EXEMPT_PATHS = frozenset({"/login", "/setup"})
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def path_is_exempt(path: str) -> bool:
    normalized = (path or "/").rstrip("/") or "/"
    return normalized in CSRF_EXEMPT_PATHS


async def enforce_csrf(request: Request) -> None:
    """Global dependency: reject unsafe cookie-authenticated requests without a token."""
    if request.method not in UNSAFE_METHODS:
        return
    if path_is_exempt(request.url.path):
        return
    if not request.cookies.get(settings.SESSION_COOKIE_NAME):
        # Anonymous requests are handled by authentication (401), not CSRF.
        return
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    submitted = request.headers.get(CSRF_HEADER_NAME)
    if not submitted:
        content_type = request.headers.get("content-type", "").lower()
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            form = await request.form()
            value = form.get(CSRF_FORM_FIELD)
            submitted = value.strip() if isinstance(value, str) else None
    if (
        not cookie_token
        or not submitted
        or not secrets.compare_digest(cookie_token, submitted)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "رمز التحقق من الطلب (CSRF) مفقود أو غير صالح. "
                "أعد تحميل الصفحة وحاول مرة أخرى."
            ),
        )
