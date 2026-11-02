from pathlib import Path

from app.modules.maintenance.router import router


ROOT = Path(__file__).resolve().parents[1]
PLAN_TEMPLATE = ROOT / "app/modules/maintenance/templates/maintenance_plans.html"
RULES_TEMPLATE = ROOT / "app/modules/maintenance/templates/maintenance_rules_model_only.html"
ROUTER_SOURCE = ROOT / "app/modules/maintenance/router.py"


def _route_paths():
    return {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}


def test_maintenance_plan_routes_cover_page_management_and_execution():
    paths = _route_paths()
    assert ("/maintenance/plans", ("GET",)) in paths
    assert ("/api/maintenance/plans", ("GET",)) in paths
    assert ("/api/maintenance/plans", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}", ("PUT",)) in paths
    assert ("/api/maintenance/plans/{plan_id}", ("DELETE",)) in paths
    assert ("/api/maintenance/plans/bulk-delete", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/approve", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations", ("GET",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations/bulk", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations/{operation_id}", ("DELETE",)) in paths
    assert ("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}/condition", ("POST",)) in paths
    assert ("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}/condition", ("PATCH",)) in paths
    assert ("/api/maintenance/plan-execution", ("POST",)) in paths


def test_maintenance_plan_ui_exposes_complete_controls():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="btnAdd"' in html
    assert 'aria-haspopup="menu"' in html
    assert 'aria-controls="addMenu"' in html
    assert 'id="addMenu"' in html and 'hidden>' in html
    assert 'id="menuNewPlan"' in html and 'data-action="new-plan"' in html
    assert 'id="menuAddPlanOperations"' in html and 'data-action="add-plan-operations"' in html
    assert 'id="menuNewStandalone"' in html and 'data-action="new-standalone"' in html
    assert "🔧 إضافة عملية مستقلة" in html
    assert html.index('id="modelFilter"') < html.index('id="addSplit"') < html.index('id="search"')
    assert all(
        html.index(f'id="{section}"') < html.index('id="summaryPlans"')
        for section in ("editor", "operationsPanel", "standalonePanel", "executionPanel")
    )
    # قائمة الإجراءات الموحّدة لكل صف بدل الأزرار الدائمة المتعددة.
    assert 'data-action-toggle=' in html
    assert 'data-action-menu' in html
    assert 'data-menu-action=' in html
    assert "is_approved" in html
    assert 'data-remove-op="' in html
    # إجراءات الخطة متميزة وواضحة داخل القائمة.
    for label in ("إدارة العمليات", "تعديل الخطة", "اعتماد الخطة", "تنفيذ الخطة", "حذف الخطة"):
        assert label in html
    # إجراءات العملية المستقلة مميزة عن إجراءات الخطة.
    for label in ("تعديل شرط العملية", "إزالة من هذا الطراز", "حذف العملية من المكتبة"):
        assert label in html
    # لا أزرار إجراءات دائمة ولا عمود إجراءات منفصل بعد التوحيد.
    for legacy in ('data-edit="', 'data-approve="', 'data-ops="', 'data-execute="', 'data-edit-standalone="'):
        assert legacy not in html
    assert 'id="form" class="toolbar" style="padding:18px;flex-wrap:wrap" data-em-root' in html
    assert 'id="standaloneForm" class="toolbar" style="padding:18px;flex-wrap:wrap" data-em-root' in html
    assert 'id="executionPanel"' in html
    assert 'id="executionForm" class="toolbar" style="padding:18px;flex-wrap:wrap" data-em-root' in html
    assert 'id="executionEquipment"' in html
    assert 'id="executionDate"' in html
    assert 'id="executionMeter"' in html
    assert "api+'/plan-execution'" in html
    assert "لا يتم تعديل شروط العمليات من هنا." in html
    assert "remove-impact" in html
    assert "إزالة ارتباط عملية بالخطة" in html
    assert 'id="savePlanOps"' in html
    assert "EditManager.register(planOpsProvider" in html
    assert "EditManager.register(standaloneLinksProvider" in html
    assert "pendingStandaloneRemovals.add(Number(operationId))" in html
    assert "saveStandaloneLinkRemovals" in html
    assert "لديك تغييرات روابط غير محفوظة لهذا الطراز" in html
    assert "EditManager.commit('إزالة ارتباط عملية مستقلة بالطراز')" in html


def test_plan_operation_add_rejects_inactive_operation():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert 'if not operation.is_active:' in source
    assert 'لا يمكن إضافة عملية صيانة غير مفعلة إلى الخطة' in source


def test_plan_operations_are_added_only_from_the_operation_library():
    """اختيار عمليات المكتبة يجري داخل نافذة صفحة الخطط ويحفظ دفعة واحدة."""
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert "📚 إضافة من المكتبة العامة أو مكتبة هذا الطراز" in html
    assert 'id="openOperationLibrary"' in html
    assert "$('openOperationLibrary').onclick=openPlanOperationPicker" in html
    assert 'id="planOperationPicker"' in html
    assert 'id="pickerLibraryModel"' in html and 'id="pickerLibraryGeneral"' in html
    assert 'role="group" aria-label="مصدر عمليات الصيانة"' in html
    assert 'id="planOperationSearch"' in html
    assert 'id="planOperationSelectAll"' in html
    assert 'id="planOperationSelectedCount"' in html
    assert "api+'/model-operations?equipment_model_id='+modelId" in html
    assert "sourceLabel=operation.source==='model'?'عملية خاصة بهذا الطراز':'عملية عامة'" in html
    assert "model_operation_ids:selected.filter(item=>item.source==='model').map(item=>item.id)" in html
    assert "api+'/plans/'+planId+'/operations/bulk'" in html
    assert "/maintenance/rules?plan_id=" not in html
    picker = html[html.index('id="planOperationPicker"'):html.index('id="planTargetPicker"')]
    assert "حذف العملية" not in picker and "تعديل العملية" not in picker
    assert "interval_km" not in picker and "شرط استحقاق" not in picker
    assert "function setPickerLibrary(library)" in html
    assert "capturePlanPickerSelection()" in html
    assert "pickerLibrary='model'" in html


def test_add_menu_opens_both_libraries_for_a_plan_of_the_selected_model():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="planTargetPicker"' in html
    assert "async function addPlanOperationsFromAddMenu()" in html
    assert "plans.filter(plan=>Number(plan.equipment_model_id)===modelId)" in html
    assert "if(!plans.length){await openPlanOperationPickerForModel(modelId);return}" in html
    assert "pendingPlanOperations=selected" in html
    assert "async function savePendingPlanOperations(planId)" in html
    assert "openLibraryAfterPlanSave=true" in html
    assert "await openPlanOperationPickerForModel(plan.equipment_model_id,plan)" in html


def test_standalone_operations_can_use_general_or_selected_model_library():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="standaloneLibraryModel"' in html
    assert 'id="standaloneLibraryGeneral"' in html
    assert 'id="standaloneModelLibraryOptions"' in html
    assert "$('standaloneLibraryModel').onclick=()=>setStandaloneLibrary('model')" in html
    assert "$('standaloneLibraryGeneral').onclick=()=>setStandaloneLibrary('general')" in html
    assert "api+'/model-operations/'+id" in html
    assert "is_active:true" in html
    assert "مفعّلة وتظهر مستقلة تلقائيًا" in html
    assert "const modelSpecific=state.modelOperations.filter(operation=>operation.is_active" in html


def test_operation_library_plan_mode_keeps_the_full_add_workflow():
    """النافذة المستقلة تحفظ شرط الطراز عبر نقطة نهاية العلاقة المخصصة."""
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert '<dialog class="maintenance-modal" id="standalonePanel"' in html
    assert "api+'/operations/'+opId+'/models/'+modelId+'/condition'" in html
    assert "method:$('standaloneOpId').value?'PATCH':'POST'" in html
    assert "equipment_model_conditions:conditions" not in html


def test_plan_selection_checkboxes_use_set_and_never_blank_the_table():
    """مربع «تحديد الكل» ومربعات الصفوف موجودة، والتحديد يعتمد على Set.has لا Set.includes.

    السبب الجذري لفراغ الجدول عند اختيار الطراز: كان صف الخطة يستدعي
    ``state.selectedPlans.includes(p.id)`` بينما ``selectedPlans`` من نوع ``Set``،
    فيرمي ``TypeError`` أثناء ``render()`` قبل إسناد ``innerHTML``، فلا يُرسم أي صف.
    """
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")

    # التحديد الفردي والجماعي باقٍ: مربع رأس الجدول + مربعات الصفوف.
    assert 'id="selectAllPlans"' in html
    assert 'class="plan-check"' in html

    # يجب استخدام Set.has؛ واستخدام Set.includes يمنع رسم الجدول بالكامل.
    assert "selectedPlans.has(" in html
    assert "selectedPlans.includes" not in html
    assert ".includes(p.id)" not in html


def test_plan_operations_load_failure_does_not_blank_the_table():
    """فشل تحميل عمليات خطة واحدة لا يمنع عرض بقية الخطط، ويُسجَّل الخطأ الحقيقي."""
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")

    assert "Promise.allSettled" in html
    assert "console.error" in html


def test_plan_list_exposes_bulk_selection_and_scoped_bulk_actions():
    """شريط التحديد يعرض عدّاد الخطط المحددة وإجراءين مقيّدين بنوع التحديد."""
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="bulkBar"' in html
    assert 'id="plansSelectedCount"' in html
    assert 'id="bulkDeletePlans"' in html
    assert 'id="bulkRemoveStandalone"' in html

    # تحديد الخطط وتحديد العمليات المستقلة مجموعتان منفصلتان.
    assert 'id="selectAllPlans"' in html
    assert 'id="selectAllStandalone"' in html
    assert "selectedPlans" in html
    assert "selectedStandalone" in html

    # الحذف الجماعي الحقيقي عبر نقطة النهاية الخادمية.
    assert 'api+"/plans/bulk-delete"' in html
    # إزالة العمليات المستقلة تبقى على نقطة نهاية إزالة الطراز الواحدة.
    assert "api+'/operations/'+operationId+'/models/'+modelId" in html
    assert "saveStandaloneLinkRemovals" in html


def test_operation_library_bulk_delete_consumes_success_and_rejected_contract():
    """معالج الحذف يستهلك أسماء استجابة الخادم ويعرض الرفض الجزئي دون نجاح زائف."""
    html = RULES_TEMPLATE.read_text(encoding="utf-8")
    handler_start = html.index("$('bulkDeleteBtn').onclick")
    handler_end = html.index("$('newOperationBtn').onclick", handler_start)
    handler = html[handler_start:handler_end]

    assert "response.ok" in handler
    assert "Number.isInteger(data.success)" in handler
    assert "Array.isArray(data.rejected)" in handler
    assert "data.rejected.map" in handler
    assert "data.deleted" not in handler
    assert "await load()" in handler
    assert "تعذر تأكيد نتيجة الحذف الجماعي" in handler
    assert "finally" in handler
    assert "this.disabled = false" in handler


def test_operation_library_preserves_loaded_rows_when_refresh_fails():
    """فشل الاتصال المؤقت لا يمسح آخر بيانات سليمة من جدول العمليات."""
    html = RULES_TEMPLATE.read_text(encoding="utf-8")
    render_start = html.index("function render(){")
    render_end = html.index("$('operationsBody').addEventListener", render_start)
    render = html[render_start:render_end]
    load_start = html.index("async function load(){")
    load_end = html.index("$('operationForm').addEventListener", load_start)
    load = html[load_start:load_end]

    assert "hasLoadedOperations" in render
    assert "state.groups=[]; state.operations=[];" not in load
    assert "ما زالت آخر بيانات محمّلة ظاهرة" in load


def test_operation_library_bulk_selection_handles_rendered_rows():
    """تُربط تغييرات تحديد الصفوف بعد رسمها وتزامن مربعي تحديد الكل."""
    html = RULES_TEMPLATE.read_text(encoding="utf-8")
    selection_start = html.index("function updateBulkActionUI()")
    selection_end = html.index("// Bulk delete handler", selection_start)
    selection = html[selection_start:selection_end]

    assert "input[id=\"selectAllOperations\"]" in selection
    assert "$('operationsBody').addEventListener('change'" in selection
    assert "document.querySelectorAll('.operation-checkbox').forEach" in selection
