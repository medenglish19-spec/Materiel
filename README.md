# Materiel — إدارة العتاد والأصول

نظام إدارة أسطول ومعدات: بيانات أساسية (فئة ← نوع ← طراز) ← معدات ← حركات وقياسات
← صيانة وأعطال وإطارات وبطاريات ووقود ← لوحة مؤشرات وتنبيهات موحّدة.

## المتطلبات

- Python 3.11 (ما يستخدمه CI) أو أحدث (المحلي 3.14)
- SQLite — ملف `fleet_assets.db` يُنشأ تلقائيًا عند أول تشغيل

## التثبيت

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## التشغيل

```bash
python run_web.py
# ثم افتح: http://localhost:8000
```

متغيرات بيئية مدعومة: `DATABASE_URL` · `SECRET_KEY` · `APP_HOST` · `APP_PORT` ·
`ACCESS_TOKEN_EXPIRE_MINUTES` · `LOG_LEVEL` · `LOG_DIR`

## أي قاعدة بيانات يعمل عليها التطبيق

**خادم التطوير يشير إلى نسخة، لا إلى `fleet_assets.db`.**

`init_db()` ينفّذ `alembic upgrade head` عند كل إقلاع. ومع `--reload` يُعاد
الإقلاع عند كل حفظ، فأي تعديل على ملف في `migrations/versions/` يُطبَّق على قاعدة
البيانات أثناء العمل، دون أن يقرر أحد ذلك. حدث هذا فعلًا: تعديل على
`stage12_spare_parts_complete` طُبِّق على القاعدة الحيّة أثناء إعادة تحميل
تلقائية لجلسة أخرى.

انسخ القاعدة أولًا، ثم وجّه `DATABASE_URL` إليها:

```bash
cp fleet_assets.db /tmp/fleet_assets.dev.db
DATABASE_URL=sqlite:////tmp/fleet_assets.dev.db python run_web.py
```

```powershell
Copy-Item fleet_assets.db fleet_assets.dev.db
$env:DATABASE_URL = "sqlite:///./fleet_assets.dev.db"; python run_web.py
```

أما القاعدة الحيّة فتُرقَّم مرة واحدة **مقصودة**:

```bash
python -m alembic upgrade head
```

ملفات `fleet_assets_backup_*.db` في جذر المستودع بقايا نسخ يدوية متفرقة؛ النسخ
المسار أعلاه يكفي ولا داعي تراكمها في Git.

### كيف تتأكد ممّا حدث

سطر واحد عند الإقلاع يقول أي قاعدة بيانات يعمل عليها:

```
Startup facts: commit=726a44a routes=194 database=sqlite:///./fleet_assets.db
```

وكل migration مُطبَّقة تظهر في `logs/app.log` باسم ملفها، فمراجعة السجل تكفي لمعرفة
ما طرأ على أي قاعدة.

## الدخول

`admin` / `Admin@123` — يُنشأ عند أول تشغيل إن لم يوجد.

## قبل النشر: تحذيران يقاطعان الإقلاع في السجل فقط

عند كل إقلاع يفحص التطبيق إعدادين ويكتبهما كـ`WARNING` في السجل (`logs/app.log`
والـstderr). **لا يمنعان الإقلاع ولا يغيّران كلمة المرور** — قرار متعمَّد:
التطوير المحلي يجب أن يبقى يعمل بلا خطوات إضافية. لكن قبل أي نشر عيّن:

| التحذير | الخطر | الحل |
|---|---|---|
| `SECRET_KEY` هو القيمة الافتراضية | أي شخص يقرأ هذا الملف يستطيع **تزوير جلسة دخول** وتغيير أي بيانات | `SECRET_KEY=<32+ حرفاً عشوائية>` في متغيّرات البيئة — ولا في الإنتاج فقط، فأي بيئة مشتركة تستخدم نفس المفتاح |
| `admin` ما زال بكلمة المرور الافتراضية | كلمة المرور منشورة في هذا الملف وفي تاريخ المستودع | غيّرها من صفحة **المستخدمين** (لا سجلات تُكتب تلقائياً) |

عند الإقلاع على قاعدة جديدة/فارغة يُكتب تحذير ثالث: سيُنشأ `admin` بكلمة المرور
الافتراضية.

القيمة الافتراضية لـ`SECRET_KEY` موجودة في `app/core/config.py` باسم
`DEFAULT_SECRET_KEY`، والفحص نفسه في `security_warnings()` (قراءة فقط، لا يكتب).

## الاختبارات

```bash
.venv\Scripts\python -m pytest -q
```

الحالة آخر تشغيل: **319 ناجح، 1 متخطى، 0 فشل**.
ملاحظة: `tests/test_run_web_smoke.py` يشغّل خادمًا على المنفذ 8000، فيفشل إن كان
المنفذ مشغولًا مسبقًا.

## التوثيق والخريطة

| الملف | الغرض |
|---|---|
| `PROJECT_MAP.md` | ذاكرة المشروع: التقنية، تدفق النظام، المعمارية، النواقص |
| `docs/MATERIEL_EXECUTION_MAP.md` | قواعد العمل التفصيلية — اقرأه قبل أي تعديل |
| `app/modules/*/README*.md` | توثيق وحدتي الصيانة وسجل العدادات |

## الوحدات

`equipment_types` (البيانات الأساسية) · `equipment` · `meter_readings` · `missions` ·
`fuel` · `maintenance` · `equipment_maintenance` · `faults_repairs` · `tires` ·
`batteries` · `users` · `dashboard` · `notifications`

`notifications` طبقة تجميع: كل مزوّد يسجّل تنبيهات وحدته تلقائيًا عند استيراد
الحزمة، واللوحة تعرض القائمة الموحّدة مرتّبة حسب الخطورة.

## التسجيل (Logging)

طبقة غير حظري: `app/core/logging.py` — السجلات توضع في طابور داخل الذاكرة
(`QueueHandler`) ويكتبها خيط واحد إلى `logs/app.log` (دوّار 1MB × 3) وإلى stderr.
المستويات: DEBUG/INFO/WARNING/ERROR عبر `LOG_LEVEL` (افتراضي INFO).

## الواجهة

Jinja2 من الخادم، اتجاه RTL، بلا حزم npm. التنسيق كله في `static/css/style.css`
(طبقة `.mdx` لمساحة البيانات الأساسية + شاشة الدخول) مع هيكل الصفحة في
`web/templates/base.html`.

## CI

`.github/workflows/python-package-conda.yml`: فحص أسماء الملفات ← `compileall` ←
اختبار تعافي ترحيل SQLite 0007 ← `pytest`.