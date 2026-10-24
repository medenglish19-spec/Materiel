# وحدة الصيانة

> المرجع المعماري المعتمد لهذه الوحدة: [`docs/MAINTENANCE_ARCHITECTURE.md`](../../../docs/MAINTENANCE_ARCHITECTURE.md)

ملخص سريع:

- `models.py` — `MaintenanceOperationGroup` · `MaintenanceOperation` · `MaintenancePlan` · `MaintenancePlanOperation` · `MaintenanceRecord` · جدول العلاقة `maintenance_operation_models`.
- `services.py` — `status_for` · `operation_condition_meta` · `operation_condition_for_model` · `plan_status_for` · `effective_operations_for_equipment` · `latest_records` · `latest_readings`.
- `router.py` — صفحات الصيانة (الدورية · العمليات · الخطط · السجل · المستحقة) وواجهات JSON.
- `app/modules/equipment_maintenance/` — صفحة صيانة العتاد.

النموذج الفني: العملية هي الوحدة الفنية الأساسية، وانطباقها على الطراز علاقة مستقلة (هدف
معماري)، والخطة وسيلة تنظيم، والسجل يوثّق التنفيذ الفعلي. راجع الوثيقة المرجعية للقواعد
الاثنتي عشرة وجدول المطابقة والفجوات المعروفة قبل أي تعديل.

## موضع شروط الاستحقاق (مُثبت في الكود)

| المفهوم | الموضع |
| --- | --- |
| تعريف العملية الفنية (الاسم، الوصف، المجموعة) | `maintenance_operations` |
| شرط الاستحقاق وإعداد الإنذار **لكل طراز** | `maintenance_operation_models` (عمود `condition_source` + `interval_*` / `warning_*`) |
| شرط الخطة المستقل | `maintenance_plans.interval_*` |

قواعد ملزمة في الكود الحالي:

1. `condition_source = 'unset'` تعني «لم يُحفظ شرط لهذا الطراز»؛ تُعرض «الشرط غير محدد»
   ولا يُستنتج شرط من طراز آخر ولا من أعمدة العملية القديمة.
2. أعمدة `maintenance_operations.interval_*` / `warning_*` **مُهملة بقرار معماري**: لا يدخل
   أيٌّ منها في حساب استحقاق أو إنذار أو عرض تشغيلي، ولا تُرسل في استجابة الـAPI، ولا تُنسخ
   إلى أي طراز. تبقى في قاعدة البيانات كما هي بلا حذف وبلا ترحيل لحذفها.
3. العملية غير المرتبطة بأي طراز **عملية عامة في المكتبة**: لا استحقاق لها على أي عتاد ولا
   إنذار، ولا يُخترع لها انطباق. وعند ربطها بطراز يُحدَّد شرط تلك العلاقة صراحةً.
4. تعديل شرط طراز يتم على صف العلاقة الخاص به وحده، فلا يتأثر طراز آخر.
5. عمودا «الشرط» و«الإنذار» في جدول المكتبة يعرضان ملخصًا محسوبًا في الخدمة
   (`summarize_operation_conditions`) لا في JavaScript.
