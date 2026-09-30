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

## الدخول

`admin` / `Admin@123` — يُنشأ عند أول تشغيل إن لم يوجد. **غيّره فورًا.**

## الاختبارات

```bash
.venv\Scripts\python -m pytest -q
```

الحالة آخر تشغيل: **271 ناجح، 1 متخطى، 0 فشل**.
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