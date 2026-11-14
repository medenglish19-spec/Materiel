"""Shared pytest configuration.

Production behaviour is authentication-on.  Most of the existing suite was
written as a functional/browser suite that relies on the explicit development
bypass (``DEV_DISABLE_AUTH``) to exercise pages without a login form.  Rather
than rewriting hundreds of unrelated assertions, those tests opt into the same
bypass a developer would use manually.

The bypass tests still exercise cookie-backed sessions and unsafe writes, so
the test client echoes the double-submit CSRF token exactly like the browser
script does.  Security tests mark themselves with ``@pytest.mark.auth_enforced``
and run with authentication and role checks fully enabled; there the token is
never injected, so missing-token assertions stay meaningful.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, UNSAFE_METHODS

_ORIGINAL_REQUEST = TestClient.request


def _header_present(headers: Any, name: str) -> bool:
    if headers is None:
        return False
    if isinstance(headers, Mapping):
        return any(str(key).lower() == name.lower() for key in headers)
    return any(str(item[0]).lower() == name.lower() for item in headers)


def _request_with_csrf(self: TestClient, method: str, url: str, **kwargs: Any) -> Any:
    if settings.DEV_DISABLE_AUTH and method.upper() in UNSAFE_METHODS:
        headers = kwargs.get("headers")
        if not _header_present(headers, CSRF_HEADER_NAME):
            token = self.cookies.get(CSRF_COOKIE_NAME)
            if token:
                if isinstance(headers, Mapping):
                    headers = {**headers, CSRF_HEADER_NAME: token}
                elif headers is None:
                    headers = {CSRF_HEADER_NAME: token}
                else:
                    headers = [*headers, (CSRF_HEADER_NAME, token)]
                kwargs["headers"] = headers
    return _ORIGINAL_REQUEST(self, method, url, **kwargs)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "auth_enforced: run the test with authentication and role checks enabled",
    )


@pytest.fixture(autouse=True)
def _auth_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    enforced = request.node.get_closest_marker("auth_enforced") is not None
    monkeypatch.setattr(settings, "DEV_DISABLE_AUTH", not enforced)
    if not enforced:
        monkeypatch.setattr(TestClient, "request", _request_with_csrf)
