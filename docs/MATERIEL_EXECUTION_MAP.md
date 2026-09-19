# Materiel — خريطة التنفيذ الفعلية للمستودع

> وثيقة تنفيذية مبنية على حالة الفرع `main` الحالية. الهدف منها أن تكون مرجعًا عند تعديل أي Module دون إعادة بناء المشروع من الصفر.

## 1. قاعدة القراءة
الأولوية عند فهم النظام:
1. قاعدة البيانات وAlembic
2. SQLAlchemy Models
3. Services وقواعد العمل
4. Routers
5. Tests
6. Templates / JavaScript / CSS
7. README والوثائق التاريخية

أي تعديل يجب أن يحافظ على الموجود، وأي تعارض معماري/تجاري حقيقي يوقف الجزء المتعارض ويحتاج قرارًا صريحًا.

## 2. المسار العام
```
Master Data
  -> Model
  -> Equipment
  -> Event / Transaction
  -> History
  -> Current State
  -> Derived Calculations
  -> Notifications
  -> Dashboard / Reports
```

## 3. Master Data
### الملفات الأساسية
- `app/modules/equipment_types/models.py`
- `app/modules/equipment_types/services.py`
- `app/modules/equipment_types/router.py`
- `app/modules/equipment_types/templates/master_data_workspace.html`
- `static/js/master-data-tree.js`

### البنية
```
Category
  -> Equipment Type
     -> Equipment Model
        -> Basic Data
        -> Specifications
        -> Tire configuration
        -> Battery configuration
        -> Model-specific rules
```

### قواعد مؤكدة
- Model هو المركز الفني.
- Equipment Model مرتبط حاليًا بـ Equipment Type بعلاقة غير قابلة لـ NULL.
- Type مرتبط اختياريًا بـ Category.
- حذف Type المرتبط بطرازات ممنوع من الخدمة.
- التجميد `is_frozen` يحمي Type/Model من تعديلات معينة.
- العلامة التجارية مستقلة ويرتبط بها Model.
- خصائص Model الحرة موجودة عبر `EquipmentModelSpecDefinition` و`EquipmentModelSpecValue`.
- لا تجعل Root-level Model وظيفة حقيقية من الواجهة ما لم يتم اعتماد تغيير Schema لأن `equipment_type_id` حاليًا `nullable=False`.

## 4. Master Data Tree
### JavaScript
`static/js/master-data-tree.js`

المسؤوليات الحالية:
- البحث.
- Expand/Collapse.
- Edit/Delete.
- Context menu / Long press.
- Inline add.
- Drag & Drop.
- نقل Model.
- Undo للنقل.
- JSON export.

عقود الواجهة المهمة:
- `data-tree-edit`
- `data-tree-delete`
- `data-equipment-type-id`
- `data-category-id`
- عناصر `tree-group`
- عناصر Toast الخاصة بالتراجع.

أي تغيير لهذه العقود يجب أن يراجع اختبارات Master Data أولًا.

## 5. Equipment
### الملفات
- `app/modules/equipment/models.py`
- `app/modules/equipment/router.py`
- Services/Schemas/Templates الخاصة بالوحدة.

### الدور
Equipment يمثل الأصل الفعلي، وليس Model.

يمكن أن يرتبط بـ:
- Model
- Meter history
- Maintenance records
- Faults/Repairs
- Missions
- Fuel
- Tires
- Batteries

التحليل العددي والحالة التشغيلية يجب ألا يغيرا مصدر البيانات الأصلي.

## 6. Maintenance
### الملفات
- `app/modules/maintenance/models.py`
- `app/modules/maintenance/services.py`
- `app/modules/maintenance/router.py`
- `app/modules/equipment_maintenance/router.py` عند وجود مسار متعلق بها
- Templates/Tests الخاصة بالصيانة.

### قاعدة الأعمال
Maintenance Rule مرتبطة بالـ Model.

Maintenance Record مرتبط بـ Equipment.

```
Model
  -> Maintenance Rules

Equipment
  -> Maintenance Records
```

لا يجوز الرجوع إلى Type أو Brand لاختيار قاعدة الصيانة بدل Model.

### العداد
- km أو hours بحسب Measurement Unit للـ Equipment Type.
- الاستحقاق العدادي يعتمد على Current Meter وLast Maintenance Meter.
- الاستحقاق الزمني يعتمد على تاريخ آخر صيانة + interval_days.
- لا يتم افتراض AND/OR إذا لم تحدده القواعد الحالية.

## 7. Meter Readings
### الملفات
- `app/modules/meter_readings/models.py`
- `app/modules/meter_readings/router.py`
- Services/Audit/Excel reader الموجودة في الوحدة.

### القاعدة
Meter Reading تاريخ.

لا يتم التعامل مع `current_odometer` أو `current_hours` كمصدر تاريخ بديل عن السجل.

يجب التحقق من التسلسل الزمني ومن القراءة الأقل من قراءة سابقة وفق سياسة النظام الحالية.

### المستهلكون
- Maintenance
- Tires
- Batteries
- Fuel
- Missions
- Faults/Repairs عند الحاجة
- Dashboard

لا تنشئ كل وحدة مصدر Meter مستقلًا.

## 8. Tires
### الملفات
- `app/modules/tires/models.py`
- `app/modules/tires/router.py`
- `app/modules/tires/state_engine.py`
- Services وBatch State Loading ذات الصلة.

### النموذج
```
Tire
  -> Movement History
  -> Current State
```

الحركة:
- Install
- Remove
- Move = Remove + Install

لا يتم الكتابة فوق سجل تركيب قديم لإخفاء التاريخ.

### Model configuration
- Tire positions تخص Model.
- Tire size configuration تخص Model.
- Stock tire ليست Mounted tire.

### Dashboard
"Expired mounted tires" يجب أن يعتمد على Current State للإطارات المركبة، وليس جميع الإطارات الموجودة في المخزون.

## 9. Batteries
### الملفات
- `app/modules/batteries/models.py`
- `app/modules/batteries/services.py`
- `app/modules/batteries/router.py`
- Templates الخاصة بالبطاريات.

### النموذج
```
Battery
  -> Movement History
  -> Current State
```

الحركات:
- Install
- Remove
- Replace/Transfer عبر تاريخ الحركة.

المنطق العام مشابه للإطارات، لكن قواعد البطارية تبقى خاصة بالمجال.

## 10. Faults & Repairs
### الملفات
- `app/modules/faults_repairs/routes.py`
- `app/modules/faults_repairs/models.py`
- `app/modules/faults_repairs/services.py`
- Templates/JS الخاصة بالأعطال والإصلاح.

### العلاقات
```
Equipment
  -> Fault
     -> Repair
        -> Technician Intervention
        -> Spare Parts
```

وجود Fault لا يعني تلقائيًا أن Equipment غير متاح؛ Impact/الحالة التشغيلية هي التي تحدد الأثر.

## 11. Fuel
### الملفات
- `app/modules/fuel/router.py`
- `app/modules/fuel/models.py`
- `app/modules/fuel/services.py`

Fuel Record يرتبط بـ Equipment.

يمكن استخدام Meter History/قراءات الوقود لحساب:
- Distance
- Consumption
- Abnormality

ولا يتم الحساب من قراءة عداد غير صالحة زمنيًا.

## 12. Missions
### الملفات
- `app/modules/missions/router.py`
- `app/modules/missions/models.py`
- `app/modules/missions/services.py`

Mission مرتبطة بـ Equipment.

البيانات الأساسية قد تشمل:
- Driver
- Document
- Purpose
- Destination
- Start/End
- Departure Meter
- Return Meter
- Notes

Distance = Return Meter - Departure Meter بعد التحقق من العداد.

## 13. Dashboard
### الملفات
- `app/modules/dashboard/`
- Templates/Services الخاصة باللوحة.

Dashboard ليس مصدر حقيقة.

كل مؤشر يجب أن يكون قابلًا للتتبع إلى:
```
Source Data
  -> Domain Service
  -> Aggregation
  -> Dashboard
```

أي رابط من Indicator يجب أن يفتح صفحة تعرض نفس النطاق المنطقي للمؤشر.

## 14. Notifications
### الملفات
- `app/modules/notifications/`

الإشعار مشتق من حالة أو حدث حقيقي.

لا يجوز أن يعيد Notification تعريف Maintenance Due أو Tire Expiry بطريقة مختلفة عن Service المصدر.

## 15. Shared UI
### الملفات
- `web/templates/base.html`
- `static/css/style.css`

القواعد:
- RTL محفوظ.
- الصفحات الداخلية تعتمد على base.html.
- لا يوضع JavaScript داخل `<title>`.
- JavaScript اختياري العناصر وDefensive.
- التصميم لا يغير Business Logic.

## 16. Database & Migrations
### الملفات
- `app/database/`
- `migrations/versions/`

قبل أي Schema change:
1. افحص revision الحالي.
2. افحص Model والعلاقات.
3. افحص البيانات الموجودة.
4. افحص الاستعلامات والخدمات.
5. أنشئ Migration صغيرة ومحددة.
6. اختبر upgrade.
7. اختبر الوظائف المرتبطة.

لا تستخدم `git reset --hard` ولا تحذف بيانات قائمة لحل مشكلة.

## 17. Permissions
الأدوار المعروفة:
- ADMIN
- FLEET_MANAGER
- OPERATOR
- VIEWER

التحكم الحقيقي يجب أن يكون Backend authorization؛ إخفاء الزر وحده ليس حماية.

## 18. Tests
اختبارات Master Data الحالية تشمل عقود الشجرة، التحرير، الحقول، workflows والاستقرار العام.

اختبارات المجال يجب أن تغطي خصوصًا:
- Model-only maintenance.
- Meter chronology.
- Tire install/remove/reinstall.
- Battery install/remove/replace.
- Dashboard state filters.
- Permissions.
- Template integrity.
- Navigation/UI smoke.

## 19. طريقة تنفيذ أي مهمة
```
Requirement
  -> Identify Module
  -> Identify Source of Truth
  -> Inspect Model
  -> Inspect Service
  -> Inspect Router
  -> Inspect Template/JS/CSS
  -> Inspect Tests
  -> Check Migration impact
  -> Minimal Change
  -> Tests
  -> Regression
  -> CI
```

## 20. قاعدة التعارض
إذا كانت المهمة ممكنة ضمن البنية الحالية: نفذها مباشرة.

إذا تطلبت تغييرًا في Business Rule أو Schema أو تاريخ البيانات أو عقد API بطريقة غير متفق عليها:
- لا تتحايل.
- لا تحذف الموجود.
- أوقف الجزء المتعارض.
- اشرح التعارض.
- انتظر قرار المستخدم.

## 21. معيار الإنجاز
المهمة لا تعتبر مكتملة لمجرد أن الواجهة تظهر.

المعيار:
```
Database
+ Model
+ Service
+ Router/API
+ Permissions
+ UI
+ Tests
+ Regression
+ CI
```

مع الحفاظ على:
- البيانات التاريخية.
- مصدر الحقيقة.
- RTL.
- Mobile behavior.
- الوظائف الحالية.

## 22. المرجع المختصر
```
MASTER DATA
  ↓
MODEL
  ↓
EQUIPMENT
  ↓
EVENT / TRANSACTION
  ↓
HISTORY
  ↓
CURRENT STATE
  ↓
DERIVED CALCULATIONS
  ↓
NOTIFICATIONS
  ↓
DASHBOARD / REPORTS
```

هذه الوثيقة مرجع تنفيذي، وليست بديلًا عن فحص الكود الحالي قبل كل تغيير.
