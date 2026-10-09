import os
import pytest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

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
    <form id="serverSearchForm" method="get" action="/maintenance/records"><input id="serverSearch" name="query" type="search" placeholder="بحث خادمي"></form>
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
        channel=os.environ.get("PLAYWRIGHT_BROWSER_CHANNEL")
        browser=p.chromium.launch(headless=True,channel=channel) if channel else p.chromium.launch(headless=True);page=browser.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
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


def test_form_without_method_is_tracked_and_fetch_save_is_awaited(browser_page):
    page,errors=browser_page
    page.evaluate("""() => {
      const form=document.createElement('form'); form.id='dynamicForm';
      form.innerHTML='<input id="dynamicValue" name="value" required><button type="submit">حفظ</button>';
      document.body.appendChild(form);
      form.addEventListener('submit',async e=>{e.preventDefault();await fetch('/dynamic-save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:dynamicValue.value})});});
    }""")
    page.locator('#dynamicValue').fill('abc')
    page.wait_for_timeout(500)
    expect(page.locator('[data-em-action="save"]')).to_be_enabled()
    page.locator('[data-em-action="save"]').click()
    page.wait_for_timeout(150)
    expect(page.locator('#emStatus')).to_have_attribute('data-state','clean')
    assert not errors


def test_save_failure_keeps_page_dirty(browser_page):
    page,errors=browser_page
    page.locator('#date').fill('2026-09-29')
    page.wait_for_timeout(500)
    page.evaluate("EditManager.setSaveHandler(async()=>false)")
    page.locator('[data-em-action="save"]').click()
    page.wait_for_timeout(100)
    expect(page.locator('#emStatus')).to_have_attribute('data-state','dirty')
    assert not errors


def test_async_form_save_waits_for_api_and_retries_without_losing_input(browser_page):
    page,errors=browser_page
    attempts=[]
    def save_route(route):
        attempts.append(route.request.method)
        if len(attempts)==1:
            route.fulfill(status=422,json={"detail":[{"msg":"Value error, الكمية المتاحة للتوزيع هي 3 فقط"}]})
        else:
            route.fulfill(status=200,json={"ok":True})
    page.route("**/submit-save",save_route)
    page.evaluate("""() => {
      EditManager.setSaveHandler(null);
      const form=document.createElement('form');form.id='asyncSaveForm';
      form.innerHTML='<input id="asyncSaveValue" name="value"><button type="submit">حفظ</button>';
      document.body.appendChild(form);
      form.addEventListener('submit',async event=>{
        event.preventDefault();
        await new Promise(resolve=>setTimeout(resolve,80));
        await fetch('/submit-save',{method:'POST',body:JSON.stringify({value:asyncSaveValue.value})});
      });
    }""")
    page.locator('#asyncSaveValue').fill('keep-me')
    page.wait_for_timeout(450)
    page.evaluate("window.firstSave=EditManager.save();true")
    page.wait_for_timeout(25)
    expect(page.locator('#emStatus')).to_have_attribute('data-state','saving')
    assert page.evaluate("EditManager.isDirty()")
    assert not page.evaluate("window.firstSave")
    expect(page.locator('#emStatus')).to_have_attribute('data-state','dirty')
    expect(page.locator('#asyncSaveValue')).to_have_value('keep-me')
    expect(page.locator('#emToast')).to_contain_text('الكمية المتاحة للتوزيع هي 3 فقط')
    assert page.url.endswith('/maintenance/records')

    page.locator('#asyncSaveValue').fill('valid-value')
    page.wait_for_timeout(450)
    assert page.evaluate("EditManager.save()")
    expect(page.locator('#emStatus')).to_have_attribute('data-state','clean')
    assert attempts==['POST','POST']
    assert not errors


def test_concurrent_writes_are_all_awaited_and_repeated_save_is_guarded(browser_page):
    page,errors=browser_page
    calls=[]
    api_errors=[]
    def route_api(route):
        calls.append((route.request.method,route.request.url))
        if route.request.url.endswith('/write-b'):
            route.fulfill(status=422,json={"detail":[{"msg":"قيمة غير صالحة"}]})
        else:
            route.fulfill(status=200,json={"ok":True})
    page.route("**/write-*",route_api)
    page.evaluate("""() => {
      document.addEventListener('materiel:api-error',event=>window.apiErrors.push(event.detail));
      window.apiErrors=[];
      EditManager.setSaveHandler(async()=>{
        await new Promise(resolve=>setTimeout(resolve,60));
        const responses=await Promise.all([
          fetch('/write-a',{method:'POST'}),
          fetch('/write-b',{method:'PATCH'})
        ]);
        return responses.every(response=>response.ok);
      });
      document.querySelector('#date').value='2026-10-01';
      document.querySelector('#date').dispatchEvent(new Event('input',{bubbles:true}));
    }""")
    page.wait_for_timeout(450)
    results=page.evaluate("Promise.all([EditManager.save(),EditManager.save()])")
    assert results==[False,False]
    assert [method for method,_ in calls]==['POST','PATCH']
    assert page.evaluate("window.apiErrors.length")==1
    expect(page.locator('#emStatus')).to_have_attribute('data-state','dirty')
    expect(page.locator('#emToast')).to_contain_text('قيمة غير صالحة')
    assert not errors


def test_api_bridge_ignores_get_and_reports_post_patch_delete_once(browser_page):
    page,errors=browser_page
    events=[]
    page.route("**/method-check/**",lambda route:route.fulfill(status=500,json={"detail":"تعذر التنفيذ"}))
    page.evaluate("window.apiErrors=[];document.addEventListener('materiel:api-error',event=>window.apiErrors.push(event.detail))")
    page.evaluate("""async()=>{
      await fetch('/method-check/get');
      await fetch('/method-check/post',{method:'POST'});
      await fetch('/method-check/patch',{method:'PATCH'});
      await fetch(new Request(location.origin+'/method-check/delete',{method:'DELETE'}));
      await new Promise(resolve=>setTimeout(resolve,0));
    }""")
    assert page.evaluate("window.apiErrors.map(error=>typeof error.input==='string'?error.input:error.input.url)") == [
        '/method-check/post',
        '/method-check/patch',
        page.url.split('/maintenance/records')[0]+'/method-check/delete',
    ]
    assert not errors


def test_distribution_save_failure_refreshes_balances_without_losing_quantities(browser_page):
    page,errors=browser_page
    env=Environment(
        loader=ChoiceLoader([
            FileSystemLoader(ROOT/"app"/"modules"/"spare_parts_movements"/"templates"),
            FileSystemLoader(BASE),
        ]),
        autoescape=select_autoescape(["html"]),
    )
    distribution_html=env.get_template("distribution.html").render(request=_Request())
    posts=[]
    def distribution_api(route):
        request=route.request
        if request.method=="GET" and request.url.endswith("/available"):
            route.fulfill(status=200,json=[{
                "request_item_id":42,"request_number":"SR-42","part_name":"فلتر",
                "equipment_code":"EQ-42","received_date":"2026-10-01",
                "supplier_institution":"المورد","available_quantity":3,
            }])
        elif request.method=="GET":
            route.fulfill(status=200,json=[])
        elif request.method=="POST":
            posts.append(request.post_data_json)
            if len(posts)==1:
                route.fulfill(status=400,json={"detail":"الكمية المتاحة للتوزيع هي 3 فقط"})
            else:
                route.fulfill(status=201,json={"ok":True})
        else:
            route.fulfill(status=200,json={"ok":True})
    page.route("**/api/spare-parts-movements**",distribution_api)
    page.set_content(distribution_html,wait_until="load")
    page.wait_for_selector('#lines tr[data-id="42"]',state="attached")
    page.locator('#newBtn').click()
    page.locator('#number').fill('D-42')
    page.locator('#recipient').fill('الورشة')
    page.locator('#lines tr[data-id="42"] .qty').fill('5')
    page.locator('#save').click()
    expect(page.locator('#notice')).to_contain_text('الكمية المتاحة للتوزيع هي 3 فقط')
    expect(page.locator('#lines tr[data-id="42"] .qty')).to_have_value('5')
    assert page.locator('#emToast').count()==0 or not page.locator('#emToast').is_visible()
    page.locator('#lines tr[data-id="42"] .qty').fill('3')
    page.locator('#save').click()
    expect(page.locator('#form')).not_to_have_class('open')
    assert len(posts)==2
    assert posts[0]["items"]==[{"request_item_id":42,"quantity":5}]
    assert posts[1]["items"]==[{"request_item_id":42,"quantity":3}]
    assert page.url.endswith('/maintenance/records')
    assert not errors


def test_search_button_and_enter_run_the_same_search(browser_page):
    page, errors = browser_page
    page.evaluate("""() => {
      window.searchRuns = 0;
      document.querySelector('#search').addEventListener('input', () => window.searchRuns++);
    }""")
    page.locator('#search').fill('فلتر')
    page.evaluate("window.searchRuns = 0")
    page.locator('#search').locator("xpath=..").locator('.global-search-btn').click()
    expect(page.locator('#search')).to_have_value('فلتر')
    assert page.evaluate("window.searchRuns") == 1

    page.evaluate("window.searchRuns = 0")
    page.locator('#search').press('Enter')
    assert page.evaluate("window.searchRuns") == 1
    assert not errors


def test_server_search_button_and_enter_submit_get_form(browser_page):
    page, errors = browser_page
    page.evaluate("""() => {
      const form = document.querySelector('#serverSearchForm');
      window.submittedQueries = [];
      form.addEventListener('submit', event => {
        event.preventDefault();
        window.submittedQueries.push(new FormData(form).get('query'));
      });
    }""")
    page.locator('#serverSearch').fill('زيت')
    page.locator('#serverSearch').locator("xpath=..").locator('.global-search-btn').click()
    assert page.evaluate("window.submittedQueries") == ['زيت']
    page.locator('#serverSearch').fill('فلتر')
    page.locator('#serverSearch').press('Enter')
    assert page.evaluate("window.submittedQueries") == ['زيت', 'فلتر']
    assert not errors


def test_enter_moves_through_select_fields_and_executes_next_action(browser_page):
    page, errors = browser_page
    page.locator('#model').select_option('1')
    page.locator('#model').press('Enter')
    expect(page.locator('#equipment')).to_be_focused()
    page.locator('#equipment').press('Enter')
    expect(page.locator('#operation')).to_be_focused()
    page.locator('#operation').press('Enter')
    expect(page.locator('#date')).to_be_focused()

    page.evaluate("""() => {
      const scope = document.createElement('div');
      scope.className = 'card';
      scope.innerHTML = '<input id="enterActionInput"><button id="enterActionButton" type="button" data-enter-next>تنفيذ</button>';
      document.body.appendChild(scope);
      window.enterActionRuns = 0;
      document.querySelector('#enterActionButton').addEventListener('click', () => window.enterActionRuns++);
    }""")
    page.locator('#enterActionInput').press('Enter')
    assert page.evaluate("window.enterActionRuns") == 1
    assert not errors
