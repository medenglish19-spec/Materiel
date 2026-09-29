import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from jinja2 import Environment, FileSystemLoader, select_autoescape

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "web" / "templates"
STATIC = ROOT / "static"

class _Request:
    class URL:
        path = "/maintenance/records"
    url = URL()

def render_fixture(body):
    env = Environment(loader=FileSystemLoader(BASE), autoescape=select_autoescape(["html"]))
    t = env.from_string('{% extends "base.html" %}{% block title %}اختبار{% endblock %}{% block content %}' + body + '{% endblock %}')
    return t.render(request=_Request())

@pytest.fixture
def browser_page():
    html = render_fixture('''
    <form id="record" method="post" action="/maintenance/records/create">
      <select id="model" name="model" required><option value="">طراز</option><option value="1">طراز 1</option></select>
      <select id="equipment" name="equipment" required><option value="">عتاد</option><option value="10">عتاد 10</option></select>
      <select id="operation" name="operation" required><option value="">عملية</option><option value="20">تغيير الزيت</option></select>
      <input id="date" name="date" type="date" required><input id="meter" name="meter" type="number" min="0">
      <button type="submit">حفظ الصيانة</button>
    </form>
    <input id="search" type="search" placeholder="بحث">
    <script>
      model.onchange=()=>{equipment.value='';operation.value=''};
      equipment.onchange=()=>{operation.value='20'};
      EditManager.setSaveHandler(async()=>{const r=await fetch('/maintenance/records/create',{method:'POST',body:new FormData(record)});return r.ok});
    </script>''')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/static/js/edit-manager.js":
                p=STATIC/"js"/"edit-manager.js";data=p.read_bytes();self.send_response(200);self.send_header("Content-Type","text/javascript");self.end_headers();self.wfile.write(data);return
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(html.encode())
        def do_POST(self):
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(b'{"ok":true}')
        def log_message(self,*_): pass

    server=ThreadingHTTPServer(("127.0.0.1",0),Handler);Thread(target=server.serve_forever,daemon=True).start()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{server.server_port}/maintenance/records");yield page,errors;browser.close()
    server.shutdown()

def test_toolbar_and_search_are_clean(browser_page):
    page,errors=browser_page
    expect(page.locator('[data-em-action="undo"]')).to_be_disabled()
    expect(page.locator('#emStatus')).to_have_attribute('data-state','clean')
    page.locator('#search').fill('زيت');expect(page.locator('#emStatus')).to_have_attribute('data-state','clean');assert not errors

def test_chained_form_undo_redo_and_save(browser_page):
    page,errors=browser_page
    page.locator('#model').select_option('1');page.locator('#equipment').select_option('10');page.locator('#operation').select_option('20');page.wait_for_timeout(500)
    expect(page.locator('[data-em-action="undo"]')).to_be_enabled();page.keyboard.press('Control+z');page.wait_for_timeout(100);page.keyboard.press('Control+y');page.wait_for_timeout(100)
    page.locator('[data-em-action="save"]').click();page.wait_for_timeout(100);expect(page.locator('#emStatus')).to_have_attribute('data-state','clean');assert not errors

def test_dynamic_register_set_array_and_execute(browser_page):
    page,errors=browser_page
    result=page.evaluate('''async()=>{let rows=['a'],selected=new Set(['a']),applied=0,reverted=0;EditManager.register('fixture',{capture:()=>({rows,selected}),restore:s=>{rows=[...s.rows];selected=new Set(s.selected)}});EditManager.commit('baseline');rows.push('b');selected.add('b');EditManager.commit('add row');await EditManager.execute({label:'API add',do:async()=>{applied++},undo:async()=>{reverted++},redo:async()=>{applied++}});await EditManager.undo();await EditManager.redo();return{rows,selected:[...selected],applied,reverted,dirty:EditManager.isDirty()}}''')
    assert result['rows']==['a','b'];assert set(result['selected'])=={'a','b'};assert result['applied']==2 and result['reverted']==1;assert not errors
