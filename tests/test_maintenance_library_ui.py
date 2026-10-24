"""واجهة مكتبة عمليات الصيانة بعد فصل شروط الاستحقاق عن العملية العامة.

يحرس هذا الملف السلوك المطلوب في الواجهة والـAPI معًا:

1. حفظ عملية عامة بلا أي طراز وبلا أي شرط استحقاق.
2. ظهور العملية الجديدة في جدول المكتبة (استعلام المكتبة لا يستبعد أحدًا).
3. ظهور العمليات القديمة غير المرتبطة بطراز في الجدول نفسه.
4. بقاء واجهة بيانات الطرازات متاحة في الـAPI لبقية النظام.
5. ربط عملية بطراز مع شرط خاص بها (عبر الـAPI، لا من محرر المكتبة).
6. ربط العملية نفسها بطرازين بشروط مختلفة مع بقاء الشرطين مستقلين.
7. عدم ظهور العملية العامة في الاستحقاقات ولا في الإنذارات.
8. عدم عودة القيم القديمة إلى الـAPI ولا إلى أي حساب.
"""

from pathlib import Path

from app.database.base import Base
from tests.test_maintenance_model_conditions import (  # noqa: F401  (engine + api fixture)
    TestSession,
    _operation_payload,
    api,
    engine,
)

RULES_TEMPLATE = Path("app/modules/maintenance/templates/maintenance_rules_model_only.html")
ROUTER_SOURCE = Path("app/modules/maintenance/router.py")


def _template() -> str:
    return RULES_TEMPLATE.read_text(encoding="utf-8")


def _library_rows(client) -> list:
    response = client.get("/api/maintenance/operations")
    assert response.status_code == 200, response.text
    return response.json()


def test_rules_template_defaults_missing_selected_model_context():
    assert "{% set selected_library_model_id = selected_library_model_id|default('', true) %}" in _template()


def test_operation_editor_uses_a_compact_table_with_explicit_alarm_unit_column():
    template = _template()
    assert template.index('id="operationName"') < template.index('id="operationGroup"')
    assert '<th scope="col">الحقل</th><th scope="col">القيمة</th><th scope="col">الوحدة</th>' in template
    assert 'id="modelWarningValue"' in template
    assert 'id="modelWarningUnit"' in template
    assert "＋ إضافة محور شرط" not in template
    assert "conditionUnits.forEach(({unit,field,label})=>" in template
    assert "input.placeholder='اختياري'" in template
    assert "＋ إضافة عملية إلى مكتبة ${selectedModelName()||'الطراز المحدد'}" in template
    assert "`مكتبة عمليات الصيانة للطراز ${modelName||'المحدد'}`" in template
    assert "`عمليات الصيانة وشروطها وإنذاراتها الخاصة بطراز ${modelName}.`" in template
    assert "اختر الطراز لعرض عملياته وشروطها وإنذاراتها الخاصة." in template


def test_rules_page_avoids_duplicate_navigation_and_operation_creation_paths():
    template = _template()
    assert 'class="module-tabs"' not in template
    assert 'class="breadcrumb"' not in template
    assert 'href="/maintenance/periodic"' not in template
    assert 'id="menuNewOperation"' not in template
    assert template.count('id="newOperationBtn"') == 1
    assert "/maintenance/rules/operation-template.xlsx" not in template


def test_library_selection_updates_the_current_page_without_navigation():
    template = _template()
    selection_handler = template[template.index("function updateLibrarySelection()"):]
    selection_handler = selection_handler[:selection_handler.index("$('libraryTypeFilter').addEventListener")]
    assert "window.history.replaceState" in selection_handler
    assert "window.location.href" not in selection_handler
    assert "load();" in selection_handler
    assert "state.libraryType=event.target.value" in template
    assert "$('libraryModelFilter').addEventListener('change', updateLibrarySelection)" in template


def test_operation_editor_sends_requests_for_both_general_and_model_operations():
    template = _template()
    submit_handler = template[template.index("$('operationForm').addEventListener('submit'"):]
    submit_handler = submit_handler[:submit_handler.index("// Dropdown handling for management menu")]
    assert "url=id?`${api}/model-operations/${id}`:`${api}/model-operations`" in submit_handler
    assert "await request(url,{method,body:JSON.stringify(payload)});" in submit_handler
    assert submit_handler.index("await request(url,{method,body:JSON.stringify(payload)});") > submit_handler.index("if(state.editorMode==='model')")


# ------------------------------------------------- 1) حفظ عملية عامة


def test_a_general_operation_is_created_without_any_model_or_condition(api):
    """الاسم وحده يكفي لحفظ العملية العامة: لا طراز ولا شرط استحقاق."""
    client, _ = api
    response = client.post(
        "/api/maintenance/operations",
        json={"name": "عملية عامة بلا طراز", "equipment_model_conditions": []},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "عملية عامة بلا طراز"
    assert body["model_conditions"] == []
    assert body["condition_source"] == "none"
    assert body["condition_summary"]["condition"] is None
    # ولا قيمة قديمة تُكتب على العملية.
    assert body["equipment_model_conditions"] == []


def test_the_create_request_may_omit_the_model_conditions_field_entirely(api):
    """الواجهة لا تحتاج إرسال حقل شروط الطرازات أصلًا لعملية عامة."""
    client, _ = api
    response = client.post("/api/maintenance/operations", json={"name": "عملية عامة بحقل محذوف"})
    assert response.status_code == 201, response.text
    assert response.json()["model_conditions"] == []


def test_a_general_operation_is_not_forced_to_carry_an_interval(api):
    """لا يُشترط فاصل على سجل العملية العامة (القيد القديم أُزيل)."""
    client, _ = api
    created = client.post("/api/maintenance/operations", json={"name": "عملية بلا فاصل"}).json()
    db = TestSession()
    try:
        from app.modules.maintenance.models import MaintenanceOperation

        stored = db.get(MaintenanceOperation, created["id"])
        assert stored.interval_km is None
        assert stored.interval_hours is None
        assert stored.interval_days is None
    finally:
        db.close()


# ------------------------------------------------- 2) ظهورها في المكتبة


def test_the_new_general_operation_appears_in_the_library_list(api):
    client, _ = api
    created = client.post("/api/maintenance/operations", json={"name": "عملية تظهر في الجدول"}).json()
    names = [row["name"] for row in _library_rows(client)]
    assert "عملية تظهر في الجدول" in names
    row = next(item for item in _library_rows(client) if item["id"] == created["id"])
    # صف المكتبة يحمل ما يحتاجه الجدول: الاسم، المجموعة، الحالة، وملخص الشرط.
    assert set(row) >= {"id", "name", "group_id", "is_active", "model_conditions", "condition_summary"}


def test_the_library_query_does_not_exclude_operations_without_models(api):
    """استعلام المكتبة لا يستبعد عملية لمجرد أنها بلا طراز أو بلا شرط."""
    client, ids = api
    client.post("/api/maintenance/operations", json={"name": "عامة أ"})
    client.post("/api/maintenance/operations", json={"name": "عامة ب"})
    client.post(
        "/api/maintenance/operations",
        json=_operation_payload("مرتبطة", [{"model_id": ids["model_a"], "interval_km": 5000}]),
    )
    rows = _library_rows(client)
    assert {row["name"] for row in rows} == {"عامة أ", "عامة ب", "مرتبطة"}


# ------------------------------------------------- 3) العمليات القديمة


def test_operations_without_models_are_all_listed_with_an_explicit_general_state(api):
    """العمليات القديمة غير المرتبطة بطراز تظهر، وحالتها «عملية عامة» لا خطأ عرض."""
    client, ids = api
    for name in ("قديمة 1", "قديمة 2", "قديمة 3"):
        assert client.post("/api/maintenance/operations", json={"name": name}).status_code == 201

    rows = _library_rows(client)
    old_rows = [row for row in rows if row["name"].startswith("قديمة")]
    assert len(old_rows) == 3, "كل عملية قديمة بلا طراز يجب أن تظهر في المكتبة"
    for row in old_rows:
        assert row["model_conditions"] == []
        assert row["condition_source"] == "none"
        assert row["condition_summary"]["condition"] is None
        assert row["condition_summary"]["models_count"] == 0


def test_the_template_renders_a_general_operation_row_instead_of_skipping_it():
    """القالب يعرض العملية العامة ويُبقيها منفصلة عن صفوف مكتبات الطراز."""
    template = _template()
    # كل عملية في القائمة تُبنى إلى صف واحد، وتظل العامة متاحة في وضعها.
    assert "state.operations.filter(op=>passesColumnFilters(op))" in template
    assert "rows.map(op=>{" in template
    assert "modelMode?'<span class=\"badge info\">خاصة بالطراز</span>':''" in template
    assert "source:modelMode?'model':'general'" in template


# ------------------------------------------------- 4) قائمة الطرازات


def test_the_model_picker_loads_from_the_equipment_models_endpoint(api):
    """قائمة الطرازات تُحمّل من /api/maintenance/equipment/models الحقيقي."""
    client, ids = api
    response = client.get("/api/maintenance/equipment/models")
    assert response.status_code == 200, response.text
    models = response.json()
    assert {model["id"] for model in models} >= {ids["model_a"], ids["model_b"]}
    names = {model["name"] for model in models}
    assert {"طراز ألف", "طراز باء"} <= names
    for model in models:
        assert set(model) >= {"id", "name", "type", "brand"}


def test_the_library_template_switches_between_general_and_model_libraries():
    template = _template()
    assert 'id="libraryModelFilter"' in template
    assert "العمليات العامة" in template
    assert "scope_model_id" not in template
    assert "${api}/model-operations?equipment_model_id=${libraryModelId}" in template
    assert "مكتبة العمليات الخاصة بطراز محدد" in template


def test_the_router_exposes_the_model_picker_endpoint():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert '@router.get("/api/maintenance/equipment/models")' in source


# ------------------------------------------------- 5) الربط بطراز


def test_linking_an_operation_to_a_model_stores_that_model_condition(api):
    client, ids = api
    response = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية مرتبطة بطراز",
            [{"model_id": ids["model_a"], "interval_km": 12000}],
            warning_km=1200,  # Unified warning at operation level
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["condition_source"] == "model_conditions"
    condition = body["model_conditions"][0]
    assert condition["model_id"] == ids["model_a"]
    assert condition["condition_text"] == "12000 كم"
    # Warning is unified at operation level, shown for all linked models
    assert condition["warning_text"] == "1200 كم"
    assert condition["is_defined"] is True


def test_a_model_row_without_a_condition_is_stored_as_unset_not_rejected(api):
    """ربط طراز قبل تحديد شرطه مسموح: يُحفظ «غير محدد» ولا يُرفض الحفظ."""
    client, ids = api
    response = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية ربط بلا شرط بعد",
            [{"model_id": ids["model_a"], "condition_source": "unset"}],
        ),
    )
    assert response.status_code == 201, response.text
    condition = response.json()["model_conditions"][0]
    assert condition["is_defined"] is False
    assert condition["condition_text"] == "—"


def test_the_general_operation_is_saved_without_scoping_it_to_a_model():
    """المحرر يدعم النمطين؛ إنشاء العملية العامة لا يرسل نطاق طراز."""
    template = _template()
    assert "if(state.editorMode==='model')" in template
    assert "url=id?`${api}/model-operations/${id}`:`${api}/model-operations`" in template
    assert "equipment_model_id:modelId" in template
    # والاسم وحده يكفي لعملية عامة، كما تؤكد اختبارات API أعلاه.
    assert "if(!name){ showAlert('اسم العملية مطلوب.'" in template


def test_editing_a_general_operation_does_not_touch_existing_model_links(api):
    """حفظ تعديل العملية العامة بلا شروط طرازات لا يحذف ارتباطاتها القائمة."""
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية مرتبطة تُعدَّل لاحقًا",
            [{"model_id": ids["model_a"], "interval_km": 5000}],
            warning_km=500,
        ),
    ).json()

    # تعديل عام كما ترسله المكتبة الآن: بلا حقل شروط الطرازات إطلاقًا.
    response = client.put(
        f"/api/maintenance/operations/{created['id']}",
        json={"name": "عملية مرتبطة بعد التعديل", "warning_km": 600},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "عملية مرتبطة بعد التعديل"
    # الارتباط بالطراز وشرطه لم يُمسّا.
    assert [row["model_id"] for row in body["model_conditions"]] == [ids["model_a"]]
    assert body["model_conditions"][0]["condition_text"] == "5000 كم"


# ------------------------------------------------- 6) طرازان مستقلان


def test_the_same_operation_keeps_two_independent_model_conditions(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية طرازين",
            [
                {"model_id": ids["model_a"], "interval_days": 30},
                {"model_id": ids["model_b"], "interval_days": 90},
            ],
            warning_days=5,  # Unified warning at operation level
        ),
    ).json()
    conditions = {row["model_id"]: row for row in created["model_conditions"]}
    assert conditions[ids["model_a"]]["condition_text"] == "30 يوم"
    assert conditions[ids["model_b"]]["condition_text"] == "90 يوم"
    # Warning is unified at operation level
    assert conditions[ids["model_a"]]["warning_text"] == "5 يوم"
    assert conditions[ids["model_b"]]["warning_text"] == "5 يوم"

    # تعديل طراز واحد يترك الآخر كما هو.
    updated = client.put(
        f"/api/maintenance/operations/{created['id']}",
        json=_operation_payload(
            "عملية طرازين",
            [
                {"model_id": ids["model_a"], "interval_days": 45},
                {"model_id": ids["model_b"], "interval_days": 90},
            ],
            warning_days=5,
        ),
    ).json()
    after = {row["model_id"]: row for row in updated["model_conditions"]}
    assert after[ids["model_a"]]["condition_text"] == "45 يوم"
    assert after[ids["model_b"]]["condition_text"] == "90 يوم"
    # Warning is unified at operation level
    assert after[ids["model_a"]]["warning_text"] == "5 يوم"
    assert after[ids["model_b"]]["warning_text"] == "5 يوم"


# ------------------------------------------------- 7) لا استحقاق ولا إنذار


def test_a_general_operation_appears_in_no_due_view_and_no_alert(api, monkeypatch):
    client, ids = api
    client.post(
        "/api/maintenance/operations",
        json={
            "name": "عملية عامة صامتة",
            # قيم قديمة كبيرة: يجب ألا تُنتج أي استحقاق.
            "interval_km": 5000,
            "warning_km": 500,
            "equipment_model_conditions": [],
        },
    )
    # جدول المكتبة يُبنى في المتصفح من الـAPI، فالمصدر هو ما يجب أن يحملها.
    assert "عملية عامة صامتة" in {row["name"] for row in _library_rows(client)}
    # …لكن الصفحات التشغيلية لا تعرضها في HTML الخادم.
    assert "عملية عامة صامتة" not in client.get("/maintenance/periodic").text
    assert "عملية عامة صامتة" not in client.get("/maintenance/due").text

    # ولا يجدها مزوّد الإشعارات، ولو طابق اسمها عملية مرتبطة بطراز.
    from app.modules.notifications import providers

    db = TestSession()
    try:
        monkeypatch.setattr(providers, "latest_readings", lambda session: {})
        monkeypatch.setattr(providers, "latest_records", lambda session: {})
        notes = providers.maintenance_due_provider(db)
    finally:
        db.close()
    assert [note for note in notes if "عملية عامة صامتة" in note["title"]] == []


def test_equipment_with_the_model_only_sees_operations_linked_to_it(api):
    client, ids = api
    client.post("/api/maintenance/operations", json={"name": "عامة لا تنطبق"})
    client.post(
        "/api/maintenance/operations",
        json=_operation_payload("مرتبطة تنطبق", [{"model_id": ids["model_a"], "interval_days": 7}]),
    )
    from app.modules.maintenance.services import effective_operations_for_equipment
    from app.modules.equipment.models import Equipment

    db = TestSession()
    try:
        equipment = db.get(Equipment, ids["equipment_a"])
        names = {operation.name for operation in effective_operations_for_equipment(db, equipment)}
    finally:
        db.close()
    assert "مرتبطة تنطبق" in names
    assert "عامة لا تنطبق" not in names


# ------------------------------------------------- 8) لا قيم قديمة


def test_no_legacy_interval_or_warning_field_is_returned_by_the_api(api):
    client, ids = api
    # Only interval fields are legacy; warning_km/warning_days are now the unified warning fields at operation level
    legacy_interval_fields = {"interval_km", "interval_hours", "interval_days"}
    # عملية تُنشأ بقيم قديمة صريحة: يجب ألا تُكتب ولا تُعاد.
    created = client.post(
        "/api/maintenance/operations",
        json={
            "name": "عملية بقيم قديمة صريحة",
            "interval_km": 5000,
            "interval_hours": 250,
            "interval_days": 90,
            "warning_km": 500,
            "warning_days": 30,
            "equipment_model_conditions": [{"model_id": ids["model_a"], "interval_km": 7000}],
        },
    )
    assert created.status_code == 201, created.text
    # Legacy interval fields should not be returned
    assert legacy_interval_fields.isdisjoint(created.json().keys())
    # Warning fields ARE returned at operation level (unified warnings)
    assert "warning_km" in created.json()
    assert "warning_days" in created.json()
    for row in _library_rows(client):
        # Legacy interval fields should not be returned
        assert legacy_interval_fields.isdisjoint(row.keys())
        # Warning fields ARE returned at operation level (unified warnings)
        assert "warning_km" in row
        assert "warning_days" in row
        for condition in row["model_conditions"]:
            assert condition.get("is_defined") in (True, False)


def test_the_created_row_keeps_its_legacy_columns_empty(api):
    client, _ = api
    created = client.post(
        "/api/maintenance/operations",
        json={"name": "عملية بلا قيم قديمة", "interval_km": 5000},
    ).json()
    from app.modules.maintenance.models import MaintenanceOperation

    db = TestSession()
    try:
        stored = db.get(MaintenanceOperation, created["id"])
        assert stored.interval_km is None, "الـAPI لا يكتب القيمة القديمة على العملية"
        assert stored.warning_km is None
    finally:
        db.close()


def test_the_general_operation_condition_never_falls_back_to_legacy_values():
    """قراءة شرط طراز بلا علاقة لا تُرجع أي قيمة قديمة من العملية."""
    from decimal import Decimal

    from app.modules.maintenance.models import MaintenanceOperation
    from app.modules.maintenance.services import operation_condition_for_model

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = TestSession()
    try:
        operation = MaintenanceOperation(
            name="عملية بقيمة قديمة",
            interval_km=Decimal("5000"),
            warning_km=Decimal("500"),
        )
        db.add(operation)
        db.commit()

        condition = operation_condition_for_model(db, operation.id, 999)
        assert condition.is_defined is False
        assert condition.interval_km is None
        # Warning is at operation level, not per-model
        assert not hasattr(condition, 'warning_km')
    finally:
        db.close()


# ------------------------------------------------- لا انهيار من نداء قديم


def test_the_warning_text_helper_tolerates_the_removed_reference_keyword():
    """الوسيط القديم `reference` لم يعد يعني شيئًا، لكنه لا يُسقط القائمة بخطأ 500.

    كان استدعاء `warning_setting_text(condition, reference=True)` من نسخة قديمة
    يعيد TypeError فيتحول `/api/maintenance/operations` إلى 500 بدون أي صف.
    """
    from decimal import Decimal

    from app.modules.maintenance.services import (
        CONDITION_MODEL,
        ModelCondition,
        warning_setting_text,
    )
    from app.modules.maintenance.models import MaintenanceOperation

    condition = ModelCondition(
        condition_source=CONDITION_MODEL,
        interval_km=Decimal("5000"),
    )
    operation = MaintenanceOperation(warning_km=Decimal("500"))
    # New signature: warning_setting_text(operation, condition, reference=False)
    assert warning_setting_text(operation, condition, reference=True) == warning_setting_text(operation, condition)
    assert warning_setting_text(operation, condition, reference=True) == "500 كم"

    # والقيمة القديمة لا تظهر بحجة الوسيط القديم.
    legacy_only = ModelCondition(interval_km=Decimal("5000"))
    operation = MaintenanceOperation(warning_km=Decimal("500"))
    # New signature: warning_setting_text(operation, condition, reference=False)
    # Unset condition (no condition_source) shows "—" for warning
    assert warning_setting_text(operation, legacy_only, reference=True) == "—"


def test_the_operations_list_still_answers_200_for_every_row(api):
    """القائمة كاملة تُبنى لكل صف بلا استثناء — لا صف واحد يُسقط الاستجابة."""
    client, ids = api
    client.post("/api/maintenance/operations", json={"name": "عامة أولى"})
    client.post("/api/maintenance/operations", json={"name": "عامة ثانية"})
    client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "مرتبطة بشرطين",
            [
                {"model_id": ids["model_a"], "interval_km": 5000, "warning_km": 500},
                {"model_id": ids["model_b"], "interval_days": 30, "warning_days": 5},
            ],
        ),
    )
    response = client.get("/api/maintenance/operations")
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 3
    for row in rows:
        assert row["name"]
        assert isinstance(row["model_conditions"], list)
        assert isinstance(row["condition_summary"], dict)
