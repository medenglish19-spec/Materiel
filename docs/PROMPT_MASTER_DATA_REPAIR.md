# برومبت التنفيذ الجراحي — استعادة وظائف الإضافة وإغلاق مراجعة Master Data / Model Workspace

> **المستودع الوحيد المعتمد:** `medenglish19-spec/Materiel`
>
> **الهدف:** إصلاح الحالة الحالية بعد تدهور الشجرة واختفاء أزرار الإضافة، مع الحفاظ على Model Workspace وجميع الوظائف القائمة. لا تعِد تصميم النظام.

---

## 1. نقطة البداية الإلزامية

قبل أي تعديل:

1. افحص آخر commit فعلي على `main`.
2. افحص بالكامل:
   - `app/modules/equipment_types/templates/master_data_workspace.html`
   - `static/js/master-data-tree.js`
   - `app/modules/equipment_types/router.py`
   - `app/modules/equipment_types/schemas.py`
   - اختبارات Master Data وModel Workspace.
3. افحص كل استخدام لهذه الـattributes:
   - `data-add`
   - `data-new-ref`
   - `data-new-model-for-type`
   - `data-new-type-for-category`
   - `data-tree-add`
   - `data-tree-edit`
   - `data-tree-delete`
   - `data-copy`
   - `data-delete`
4. لا تستخدم `git reset --hard`.
5. لا تحذف تغييرات غير مرتبطة.
6. لا تعِد كتابة `master-data-tree.js` بالكامل.
7. نفّذ تعديلات جراحية فقط.

الحالة الحالية التي يجب إصلاحها ليست مرجعاً لتصميم جديد؛ هي كود قائم يجب استعادته والمحافظة عليه.

---

## 2. السبب الجذري الذي يجب معالجته

في `buildRealHierarchy()` يتم حالياً حذف عناصر الإضافة الأصلية:

```js
const addType = typeChildren.querySelector('[data-new-ref="type"]');
const addModel = modelChildren.querySelector('[data-new-ref="model"]');
if (addType) addType.remove();
if (addModel) addModel.remove();
```

هذا غير مقبول لأنه يحذف عناصر التحكم التي ينطلق منها منطق الإضافة الأصلي، ثم يحاول تعويضها بعناصر DOM جديدة.

**احذف هذا السلوك نهائياً.**

لا يجوز أن تقوم `buildRealHierarchy()` بحذف `[data-new-ref="type"]` أو `[data-new-ref="model"]`.

المطلوب أن تحافظ على عناصر الإضافة الأصلية أو تنقلها مع كل `data-*` والـhandlers اللازمة. إذا كان من الضروري إنشاء زر inline إضافي، فيجب أن يستعمل handler موجوداً فعلياً ولا يستبدل الأصل.

---

## 3. النتيجة الإلزامية للشجرة

```text
المراجع العامة
├── 🏷 العلامات التجارية
│   └── ＋ إضافة علامة
└── ⚙ الخصائص
    └── ＋ إضافة خاصية

الشجرة الهرمية
└── 📁 الفئات
    ├── ＋ إضافة فئة
    └── 📁 الفئة
        └── 🗂 أنواع العتاد
            ├── ＋ إضافة نوع عتاد
            └── 🗂 نوع العتاد
                └── 🚙 الطرازات
                    ├── ＋ إضافة طراز
                    └── 🚙 الطراز
                        ├── 📄 البيانات الأساسية
                        ├── 🛞 الإطارات
                        │   ├── مواضع الإطارات
                        │   └── المقاسات المعتمدة
                        ├── 🔋 البطاريات
                        └── ⚙ الخصائص التابعة
```

إذا وجدت نوعاً غير مصنف، يبقى ضمن مجموعة الأنواع غير المصنفة، ولا يُنقل الطراز إلى قائمة مستقلة.

العلاقة الوحيدة المعتمدة:

```text
category.id
   ↓
equipment_type.category_id
   ↓
model.equipment_type_id
```

لا تستخدم أسماء العناصر لربطها.

---

## 4. قاعدة ذهبية: لا تحذف عناصر الإضافة

يجب ألا يحتوي `buildRealHierarchy()` على:

```js
addType.remove();
addModel.remove();
```

ولا أي حذف مكافئ لعناصر:

```text
[data-new-ref="category"]
[data-new-ref="type"]
[data-new-ref="model"]
```

ولا تحذف زر `data-add="category"` أو `data-add="type"` أو `data-add="model"`.

إذا تم نقل عنصر DOM، يجب أن يبقى:

- `data-*`
- `id`
- `name`
- classes
- handlers
- العلاقة مع الـform

كما هي.

---

## 5. إضافة الفئة

يجب أن يبقى زر:

```html
<span class="tree-add" data-add="category">＋</span>
```

وزر النموذج:

```html
<button class="tree-node" data-new-ref="category" type="button">＋ إضافة فئة</button>
```

لا تنشئ Route جديدة.
لا تنشئ form ثانية.
لا تغير handler الموجود.

---

## 6. إضافة نوع العتاد

يجب أن يظهر داخل الفئة الصحيحة:

```text
📁 الفئة
└── 🗂 أنواع العتاد
    ├── ＋ إضافة نوع عتاد
    └── نوع العتاد
```

إذا استُخدم زر inline، يجب أن يحمل:

```html
data-new-type-for-category="<category_id>"
```

ويستدعي فقط:

```js
openTypeCreate(categoryId)
```

والدالة يجب أن تستخدم form `#refBody form` الموجود، وتضبط:

```js
form.querySelector('[name="category_id"]').value = String(categoryId);
```

ولا تنشئ نظام form بديل.

---

## 7. إضافة الطراز

يجب أن يظهر داخل نوع العتاد الصحيح:

```text
🗂 نوع العتاد
└── 🚙 الطرازات
    ├── ＋ إضافة طراز
    └── 🚙 الطراز
```

الزر يجب أن يحمل:

```html
data-new-model-for-type="<equipment_type_id>"
```

وعند الضغط عليه:

```js
openModelCreate(typeId)
```

وتقوم الدالة فقط بـ:

```js
if (typeof resetModel === 'function') resetModel();

const typeSelect = document.getElementById('modelType');
const categorySelect = document.getElementById('modelCategory');
const option = typeSelect?.querySelector(
  `option[value="${CSS.escape(String(typeId))}"]`
);

if (typeSelect && option) {
  typeSelect.value = String(typeId);
  if (categorySelect && option.dataset.category) {
    categorySelect.value = option.dataset.category;
  }
}

if (typeof title === 'function') {
  title('إضافة طراز', 'الطرازات');
}

if (typeof show === 'function') {
  show(document.getElementById('modelPanel'));
}
```

لا تفتح صفحة منفصلة.
لا تنشئ Workspace ثانية.

---

## 8. إعادة بناء الشجرة بأمان

`buildRealHierarchy()` يجب أن تكون idempotent:

- لا تكرر العقد.
- لا تكرر أزرار الإضافة.
- لا تكرر قسم `أنواع العتاد` داخل الفئة.
- لا تكرر قسم `الطرازات` داخل النوع.
- لا تفقد العناصر الأصلية.
- لا تعتمد على أسماء الطرازات أو الأنواع.
- لا تعتمد على تنفيذ `DATA` قبل تهيئتها.

يجب الحفاظ على فحص:

```js
if (typeof DATA === 'undefined') return;
```

ويجب أن يبقى بناء الشجرة بعد جاهزية `DATA` كما هو في الإصلاح السابق.

إذا احتاجت الصفحة لإعادة البناء بعد تحديث البيانات، فلا تستخدم:

```js
if (categoryRoot.dataset.hierarchyBuilt === '1') return;
```

بطريقة تمنع التحديث بعد إضافة عنصر جديد. استخدم flag فقط لمنع البناء المتكرر في نفس دورة التهيئة، أو أعد ضبطه عند تحديث المصدر ثم أعد البناء من DOM الحالي.

---

## 9. لا تستخدم clone إذا كان سيكسر handlers

تجنب:

```js
const typeClone = typeNode.cloneNode(true);
```

إذا كان العنصر الأصلي يحمل handlers أو حالة يجب المحافظة عليها.

الأفضل نقل العنصر الأصلي:

```js
typeList.appendChild(typeNode);
```

إذا كان لا بد من clone، يجب إثبات أن جميع الأحداث تعتمد على delegation وأن كل `data-*` اللازمة بقيت موجودة.

طبّق نفس القاعدة على الطرازات.

---

## 10. Model Workspace

لا تعِد بناءه.

يجب الحفاظ على:

```js
setupModelWorkspace()
window.MATERIEL_MODEL_WORKSPACE_SELECT
```

والأقسام:

```text
basic = 0
tires = 1
positions = 1
sizes = 1
batteries = 2
specs = 3
```

والسلوك:

```js
window.MATERIEL_MODEL_WORKSPACE_SELECT?.(0);
```

للطراز نفسه، و:

```js
window.MATERIEL_MODEL_WORKSPACE_SELECT?.(1, {focus:true});
```

للإطارات، و:

```js
window.MATERIEL_MODEL_WORKSPACE_SELECT?.(2, {focus:true});
```

للبطاريات، و:

```js
window.MATERIEL_MODEL_WORKSPACE_SELECT?.(3, {focus:true});
```

للخصائص.

يجب ألا تبقى أقسام قديمة ظاهرة فوق القسم الجديد.

---

## 11. event listeners

افحص كل:

```js
tree.addEventListener('click', ...)
```

يجب ألا يكون هناك handler عام يلتقط زر إضافة قبل handler الخاص به.

ترتيب المعالجة الإلزامي:

1. إضافة/تعديل/حذف/نسخ.
2. إضافة موضع/مقاس.
3. الأسهم.
4. اختيار العقدة.
5. اختيار قسم الطراز.

عند الضغط على زر إجراء يجب:

```js
event.preventDefault();
event.stopPropagation();
return;
```

لكن لا تستخدم selector عاماً يستبعد عناصر صحيحة من البحث أو الاختيار بطريقة تكسر الوظائف.

---

## 12. data attributes

لا تغيّر أسماء attributes الحالية إلا إذا أثبتت ضرورة ذلك.

يجب أن تبقى متوافقة مع الـtemplate والـhandlers:

```text
data-add
 data-new-ref
 data-new-model-for-type
 data-new-type-for-category
 data-tree-add
 data-tree-edit
 data-tree-delete
 data-copy
 data-delete
```

أي تغيير يجب أن يشمل كل المستهلكين له في نفس التعديل.

---

## 13. وحدة القياس

ممنوع تغييرها.

يجب أن يبقى dropdown الحالي:

```html
<select name="measurement_unit" required>
  <option value="km">كم</option>
  <option value="hours">ساعات</option>
</select>
```

ويجب الحفاظ على `MEASUREMENT_UNITS` الموجود في:

```text
app/modules/equipment_types/schemas.py
```

لا تحولها إلى input.
لا تنشئ enum أو قائمة جديدة.

---

## 14. Routes

لا تنشئ Routes بديلة إذا كانت الموجودة تؤدي الغرض.

تحقق من عمل Routes الحالية لـ:

- category create/edit/delete
- equipment type create/edit/delete
- model create/edit/delete/copy
- tires
- batteries
- specs

لا تغير backend logic إلا إذا ثبت أن الخطأ Backend فعلاً.

---

## 15. Model-to-model isolation

عند الانتقال من طراز A إلى طراز B:

- يجب ألا تبقى بيانات A في B.
- يجب ألا يبقى section active من A إذا كان B يحتاج basic.
- يجب أن تستخدم كل البيانات `model_id` الحقيقي.
- لا تعتمد على اسم الطراز.

اختبر طرازين مختلفين فعلياً.

---

## 16. الإطارات

لا تحذف:

- مواضع الإطارات.
- المقاسات المعتمدة.
- أزرار إضافة الموضع.
- أزرار إضافة المقاس.
- الاستيراد.
- البيانات الموجودة في `modelPanel`.

عند الضغط على `🛞 الإطارات` يجب عرض قسم الإطارات داخل نفس `#modelPanel`.

---

## 17. البطاريات والخصائص

عند الضغط على:

```text
🔋 البطاريات
```

يجب عرض بيانات البطاريات للطراز المحدد فقط.

وعند:

```text
⚙ الخصائص التابعة
```

يجب عرض خصائص الطراز المحدد فقط.

لا تخلط بيانات عامة مع بيانات الطراز.

---

## 18. اختبارات Regression إلزامية

أضف/حدّث اختبارات حقيقية، وليس مجرد assertions نصية شكلية، للتحقق من:

1. وجود زر إضافة الفئة.
2. وجود إضافة العلامة التجارية.
3. وجود إضافة الخاصية العامة.
4. وجود إضافة نوع العتاد داخل الفئة.
5. وجود إضافة طراز داخل النوع.
6. بقاء مواضع الإطارات والمقاسات.
7. وجود handlers للـattributes الجديدة عند استخدامها.
8. عدم حذف `data-new-ref="type"` و`data-new-ref="model"` أثناء البناء.
9. اختيار الطراز يفتح basic.
10. tires يفتح القسم 1.
11. batteries يفتح القسم 2.
12. specs يفتح القسم 3.
13. عدم اختلاط طرازين.
14. إضافة النوع تحت category الصحيح.
15. إضافة الطراز تحت type الصحيح.
16. استمرار dropdown وحدة القياس بالقيم الحالية.
17. عدم كسر البحث والأسهم والنسخ والحذف والاستيراد.

---

## 19. اختبار المتصفح

إذا كان Playwright/Browser متاحاً:

نفّذ فعلياً:

1. افتح `/equipment-types`.
2. تحقق من الشجرة ومساحة العمل جنباً إلى جنب على سطح المكتب.
3. تحقق من `＋ إضافة فئة`.
4. افتح فئة وتحقق من `＋ إضافة نوع عتاد`.
5. افتح نوعاً وتحقق من `＋ إضافة طراز`.
6. افتح طرازاً.
7. تحقق من basic.
8. تحقق من tires.
9. تحقق من batteries.
10. تحقق من specs.
11. انتقل لطراز ثانٍ وتحقق من عدم اختلاط البيانات.
12. نفّذ إضافة نوع في بيئة الاختبار وتحقق من مكانه.
13. نفّذ إضافة طراز في بيئة الاختبار وتحقق من مكانه.

إذا لم يتوفر اختبار متصفح فعلي، لا تدّعِ نجاح العرض البصري؛ اذكر ذلك في التقرير النهائي.

---

## 20. الفحص النهائي

بعد التعديل:

- Syntax check.
- Imports.
- Routes.
- Templates.
- JavaScript parsing/static checks.
- Tests.
- SQLite/Alembic recovery checks الموجودة في CI.
- GitHub Actions.

لا تعتبر المهمة منتهية إذا فشل CI.

---

## 21. Git

لا تستخدم:

```bash
git reset --hard
```

بعد نجاح جميع الفحوصات أنشئ commit برسالة واضحة، مثلاً:

```text
fix(master-data): restore hierarchy actions without breaking workspace
```

ثم تحقق من CI على نفس الـcommit.

---

## 22. ممنوعات صريحة

ممنوع:

- إعادة تصميم Master Data.
- إنشاء Workspace ثانية.
- نقل بيانات الطراز أسفل الشجرة خارج مساحة العمل.
- إنشاء شجرة جديدة مستقلة.
- إعادة كتابة `master-data-tree.js` بالكامل.
- حذف أي وظيفة قائمة.
- إخفاء أزرار الإضافة بدلاً من إصلاحها.
- إنشاء Routes بديلة بلا حاجة.
- تغيير وحدة القياس.
- تغيير علاقة category → type → model.
- استخدام أسماء العناصر بدلاً من IDs.
- استخدام CSS لإخفاء أخطاء JavaScript.
- اعتبار نجاح unit tests وحده دليلاً على نجاح UI.

---

## 23. معيار النجاح النهائي

الصفحة يجب أن تكون:

```text
مركز البيانات الأساسية

┌──────────────────────┬────────────────────────────────────┐
│ شجرة مركز البيانات   │ مساحة العمل                        │
│                      │                                    │
│ 📁 الفئات            │ 🚙 الطراز المحدد                  │
│  ＋ إضافة فئة        │                                    │
│  └─ الفئة            │ 📄 البيانات الأساسية              │
│      └─ أنواع العتاد │ 🛞 الإطارات                        │
│          ＋ إضافة نوع│ 🔋 البطاريات                       │
│          └─ النوع    │ ⚙ الخصائص التابعة                 │
│              └─      │                                    │
│                 🚙   │                                    │
│              ＋ طراز │                                    │
└──────────────────────┴────────────────────────────────────┘
```

**النجاح يعني أن الإضافة والتعديل والحذف والنسخ والبحث والأسهم والشجرة وModel Workspace كلها تعمل معاً، وليس مجرد ظهور `.layout` أو `.editor`.**

---

## 24. التقرير النهائي الإلزامي

بعد التنفيذ أعطني:

1. السبب الجذري الفعلي.
2. الملفات المعدلة.
3. كل تغيير جوهري في كل ملف.
4. كيف تم استعادة أزرار الإضافة.
5. كيف تم الحفاظ على `category → type → model`.
6. كيف تم الحفاظ على Model Workspace.
7. الاختبارات المنفذة ونتائجها.
8. هل تم اختبار المتصفح فعلياً أم لا.
9. رقم commit.
10. نتيجة CI على نفس الـcommit.

**لا تنتقل إلى وحدة أخرى. لا تعتبر المهمة مغلقة حتى يتم إغلاق مراجعة Master Data / Model Workspace بالكامل.**
