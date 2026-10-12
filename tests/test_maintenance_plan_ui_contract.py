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
    assert ("/api/maintenance/plans/{plan_id}/approve", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations", ("GET",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations/{operation_id}", ("DELETE",)) in paths
    assert ("/api/maintenance/plan-execution", ("POST",)) in paths


def test_maintenance_plan_ui_exposes_complete_controls():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="btnNewPlan"' in html
    assert 'data-edit="' in html
    assert 'data-approve="' in html
    assert "is_approved" in html
    assert 'data-ops="' in html
    assert 'data-execute="' in html
    assert 'data-remove-op="' in html
    assert 'id="executionPanel"' in html
    assert 'id="executionForm"' in html
    assert 'id="executionEquipment"' in html
    assert 'id="executionDate"' in html
    assert 'id="executionMeter"' in html
    assert "api+'/plan-execution'" in html
    assert "لا يتم تعديل شروط العمليات من هنا." in html
    assert "سيتم إزالة العملية من الخطة فقط" in html


def test_plan_operation_add_rejects_inactive_operation():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert 'if not operation.is_active:' in source
    assert 'لا يمكن إضافة عملية صيانة غير مفعلة إلى الخطة' in source


def test_plan_operations_are_added_only_from_the_operation_library():
    """الإضافة الوحيدة لعمليات الخطة هي زر «📚 إضافة من مكتبة العمليات».

    يجب أن يبقى زر المكتبة هو مسار الإضافة الوحيد، وأن يختفي الزر المكرر
    «＋ إضافة العملية للخطة» مع عنصر الإضافة المضمَّن التابع له (operationSelect).
    """
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    # مسار الإضافة الوحيد: زر المكتبة وموصّله الفعلي.
    assert "📚 إضافة من مكتبة العمليات" in html
    assert 'id="openOperationLibrary"' in html
    assert "$('openOperationLibrary').onclick" in html
    assert "/maintenance/rules?plan_id=" in html
    # لا يوجد زر إضافة مكرر ولا عنصر الإضافة المضمَّن التابع له.
    assert "＋ إضافة العملية للخطة" not in html
    assert 'id="addOperation"' not in html
    assert 'id="operationSelect"' not in html


def test_operation_library_plan_mode_keeps_the_full_add_workflow():
    """مكتبة العمليات في وضع الخطة تحفظ الإضافة فعليًا عبر واجهة الخطة."""
    rules = RULES_TEMPLATE.read_text(encoding="utf-8")
    # تقرأ plan_id من العنوان وتُظهر شريط وضع الخطة.
    assert 'params.get("plan_id")' in rules
    assert "planModeBar" in rules
    # وتحفظ العمليات المختارة/المحذوفة على الخطة عبر نقاط النهاية الفعلية.
    assert 'api+"/plans/"+state.planId+"/operations"' in rules
    assert 'api+"/plans/"+state.planId+"/operations/"+operationId' in rules


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


def test_plan_list_has_no_bulk_delete_button_or_selected_counter():
    """لا زر «حذف المحدد»/«حذف المحدد (N)» ولا عدّاد «0 محددة» في جدول خطط الصيانة."""
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")

    assert "حذف المحدد" not in html
    assert "0 محددة" not in html
