import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "app" / "modules" / "spare_parts_requests" / "templates" / "requests.html"
BASE = ROOT / "web" / "templates"


class _Request:
    class URL:
        path = "/spare-parts-requests"

    url = URL()


def render_requests_page():
    source = TEMPLATE.read_text(encoding="utf-8")
    body = source.split("{% block content %}", 1)[1].rsplit("{% endblock %}", 1)[0]
    env = Environment(
        loader=ChoiceLoader([FileSystemLoader(BASE), FileSystemLoader(TEMPLATE.parent)]),
        autoescape=select_autoescape(["html"]),
    )
    template = env.from_string(body)
    parts = [
        {"id": 1, "name": "فلتر زيت", "part_number": "OIL-01"},
        {"id": 2, "name": "فلتر هواء", "part_number": "AIR-02"},
    ]
    return template.render(request=_Request(), parts=parts)


@pytest.fixture
def requests_page():
    html = render_requests_page()
    requests_data = [
        {
            "id": 101,
            "request_number": "6541",
            "request_date": "2026-10-01",
            "source_type": "repair",
            "equipment_code": "DEM-001",
            "equipment_registration": "2015132131",
            "report_number": "R-100",
            "status": "pending",
            "items": [
                {
                    "part_name": "فلتر زيت",
                    "spare_part_id": 1,
                    "requested_quantity": 3,
                    "received_quantity": 0,
                }
            ],
        },
        {
            "id": 102,
            "request_number": "6542",
            "request_date": "2026-10-02",
            "source_type": "fault",
            "equipment_code": "DEM-002",
            "equipment_registration": "2015132132",
            "report_number": "R-101",
            "status": "approved",
            "items": [
                {
                    "part_name": "فلتر هواء",
                    "spare_part_id": 2,
                    "requested_quantity": 2,
                    "received_quantity": 0,
                }
            ],
        },
    ]
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/spare-parts-requests":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
                return
            if self.path.startswith("/api/spare-parts-requests?") or self.path == "/api/spare-parts-requests":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(requests_data, ensure_ascii=False).encode())
                return
            self.send_response(404)
            self.end_headers()

        def do_DELETE(self):
            if self.path == "/api/spare-parts-requests/101":
                calls.append(("DELETE", self.path))
                self.send_response(204)
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_port}/spare-parts-requests")
        page.wait_for_load_state("networkidle")
        yield page, calls, errors
        browser.close()

    server.shutdown()


def test_requests_page_search_filters_real_rendered_rows(requests_page):
    page, calls, errors = requests_page

    expect(page.locator("#requestSearch")).to_be_visible()
    expect(page.locator("#resultCount")).to_have_text("الطلبات: 2")
    expect(page.locator("#rows .request-row")).to_have_count(2)

    page.locator("#requestSearch").fill("6541")
    expect(page.locator("#rows .request-row")).to_have_count(1)
    expect(page.locator("#rows .request-row").first).to_contain_text("6541")

    page.locator("#requestSearch").fill("فلتر هواء")
    expect(page.locator("#rows .request-row")).to_have_count(1)
    expect(page.locator("#rows .request-row").first).to_contain_text("6542")

    page.locator("#requestSearch").fill("2015132131")
    expect(page.locator("#rows .request-row")).to_have_count(1)
    expect(page.locator("#rows .request-row").first).to_contain_text("6541")

    page.locator("#requestSearch").fill("")
    expect(page.locator("#rows .request-row")).to_have_count(2)
    assert not calls
    assert not errors


def test_request_delete_keeps_existing_direct_action(requests_page):
    page, calls, errors = requests_page

    delete_button = page.locator(".request-row[data-id='101'] .delete-request")
    expect(delete_button).to_have_count(1)
    expect(delete_button).to_be_visible()
    expect(page.locator("#deleteConfirm")).to_have_count(0)

    delete_button.click()
    page.wait_for_timeout(100)

    assert calls == [("DELETE", "/api/spare-parts-requests/101")]
    assert not errors
