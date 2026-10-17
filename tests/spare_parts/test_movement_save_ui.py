import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

import pytest
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app" / "modules" / "spare_parts_movements" / "templates"
BASE = ROOT / "web" / "templates"


def _render(template_name):
    source = (TEMPLATES / template_name).read_text(encoding="utf-8")
    body = source.split("{% block content %}", 1)[1].rsplit("{% endblock %}", 1)[0]
    env = Environment(
        loader=ChoiceLoader([FileSystemLoader(BASE), FileSystemLoader(TEMPLATES)]),
        autoescape=select_autoescape(["html"]),
    )
    rendered = env.from_string(body).render()
    manager = (ROOT / "static" / "js" / "edit-manager.js").read_text(encoding="utf-8")
    toolbar = """<header style="position:sticky;top:0;z-index:50;background:white"><div class="app-workbar"><button type="button" data-em-action="undo" disabled>تراجع</button><button type="button" data-em-action="redo" disabled>إعادة</button><button type="button" data-em-action="save" disabled>حفظ</button><span id="emStatus"></span></div></header>"""
    return "<!doctype html><html><head><script>" + manager + "</script></head><body>" + toolbar + rendered + "</body></html>"


@pytest.fixture(params=[("distribution.html", "distribution"), ("return.html", "return")])
def movement_page(request):
    template, document_type = request.param
    html = _render(template)
    calls = []
    receipt = {
        "request_item_id": 7,
        "request_number": "SP-7",
        "part_name": "فلتر زيت",
        "received_quantity": 5,
        "distributed": 1,
        "returned": 0,
        "returnable_quantity": 4,
        "available_quantity": 4,
        "supplier_institution": "المؤسسة الموردة",
        "equipment_code": "EQ-7",
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlparse(self.path).path
            if path in {"/spare-parts-distribution", "/spare-parts-return"}:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
                return
            if path == "/api/spare-parts-movements/available":
                payload = [receipt]
            elif path == "/api/spare-parts-movements/returnable":
                payload = [receipt]
            elif path == "/api/spare-parts-movements":
                payload = []
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            calls.append(("POST", self.path, payload))
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    browser = sync_playwright().start()
    page = browser.chromium.launch(headless=True).new_page()
    page.goto(f"http://127.0.0.1:{server.server_port}/spare-parts-{document_type}")
    try:
        yield page, calls, document_type
    finally:
        page.context.browser.close()
        browser.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_top_save_uses_distribution_and_return_api_workflows(movement_page):
    page, calls, document_type = movement_page
    page.locator("#newBtn").click()
    if document_type == "return":
        expect(page.locator('#receipt option[value="7"]')).to_have_count(1)
    page.locator("#number").fill("DOC-2026-07")
    page.locator("#date").fill("2026-10-14")
    if document_type == "distribution":
        page.locator("#recipient").fill("مصلحة الصيانة")
        page.locator("#lines .qty").fill("2")
        expected_items = [{"request_item_id": 7, "quantity": 2}]
    else:
        page.locator("#receipt").select_option("7")
        page.locator("#returnQuantity").fill("2")
        expected_items = [{"request_item_id": 7, "received_request_item_id": 7, "quantity": 2}]

    save = page.locator('[data-em-action="save"]')
    expect(save).to_be_enabled()
    save.click()
    expect(save).to_be_disabled()
    page.wait_for_function("() => !document.getElementById('form').classList.contains('open')")

    assert len(calls) == 1
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/api/spare-parts-movements")
    assert payload["document_type"] == document_type
    assert payload["document_number"] == "DOC-2026-07"
    assert payload["items"] == expected_items
