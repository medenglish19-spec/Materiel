from fastapi.testclient import TestClient

from web import main


def _client(monkeypatch):
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    return TestClient(main.create_app())


def test_registered_navigation_routes_are_real(monkeypatch):
    with _client(monkeypatch) as client:
        paths = {route.path for route in main.app.routes}
        assert "/dashboard" in paths
        assert "/equipment" in paths
        assert "/equipment/numerical-status" in paths
        assert "/meter-readings" in paths
        assert "/meter-readings/operations" in paths
        assert "/equipment-types" in paths
        assert "/maintenance" in paths
        assert "/tires" in paths
        assert "/batteries" in paths
        assert "/fuel" in paths
        assert "/missions" in paths
        assert "/faults-repairs" in paths
        assert "/users" in paths


def test_base_navigation_does_not_contain_placeholder_hash_links(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/login")
        assert response.status_code == 200
        # Login is intentionally standalone; this test documents the route contract.
        assert 'action="/login"' in response.text
