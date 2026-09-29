"""Seed the standard maintenance operation library.

Revision ID: stage9_seed_maintenance_operation_library
Revises: stage8_remove_plan_operation_overrides

The seeded intervals are editable operational defaults, not ISO-prescribed
maintenance intervals. Actual intervals should be adjusted per manufacturer,
model and operating conditions.
"""

from alembic import op
import sqlalchemy as sa

revision = "stage9_seed_maintenance_operation_library"
down_revision = "stage8_remove_plan_operation_overrides"
branch_labels = None
depends_on = None


GROUPS = [
    ("المحرك", [
        ("فحص مستوى زيت المحرك", None, None, 7),
        ("تغيير زيت المحرك", 10000, 250, None),
        ("استبدال فلتر زيت المحرك", 10000, 250, None),
        ("فحص فلتر الهواء", 10000, 250, None),
        ("استبدال فلتر الهواء", 20000, 500, None),
        ("فحص فلتر الوقود", 10000, 250, None),
        ("استبدال فلتر الوقود", 20000, 500, None),
        ("فحص السيور والبكرات والشدادات", 20000, 500, 180),
        ("فحص تسربات الزيت والوقود", None, None, 30),
        ("فحص تهوية علبة المرافق", 20000, 500, 365),
    ]),
    ("نظام التبريد", [
        ("فحص مستوى سائل التبريد", None, None, 7),
        ("فحص حالة وتركيز سائل التبريد", None, None, 30),
        ("استبدال سائل التبريد", None, None, 730),
        ("فحص خراطيم نظام التبريد", None, None, 30),
        ("فحص المشع وتنظيفه", None, None, 180),
        ("فحص غطاء المشع", None, None, 365),
        ("فحص مضخة المياه", 40000, 1000, None),
        ("فحص منظم الحرارة", 40000, 1000, None),
        ("فحص مروحة التبريد", None, None, 180),
        ("فحص تسربات نظام التبريد", None, None, 30),
    ]),
    ("المنظومة الكهربائية", [
        ("فحص حالة البطارية", None, None, 30),
        ("فحص وتنظيف أقطاب البطارية", None, None, 90),
        ("اختبار جهد البطارية", None, None, 90),
        ("فحص نظام الشحن", None, None, 180),
        ("فحص المولد", 30000, 750, None),
        ("فحص بادئ التشغيل", 30000, 750, None),
        ("فحص الفيوزات والمرحلات", None, None, 180),
        ("فحص الأسلاك والوصلات الكهربائية", None, None, 180),
        ("فحص الإنارة والإشارات", None, None, 30),
        ("فحص أجهزة القياس والتحذيرات", None, None, 30),
    ]),
    ("نقل الحركة", [
        ("فحص مستوى زيت ناقل الحركة", None, None, 30),
        ("استبدال زيت ناقل الحركة", 40000, 1000, 730),
        ("استبدال مرشح ناقل الحركة", 40000, 1000, None),
        ("فحص القابض", 20000, 500, 180),
        ("فحص عمود نقل الحركة والمفاصل", 20000, 500, 180),
        ("فحص علبة التحويل", 40000, 1000, 730),
        ("فحص التفاضل", 40000, 1000, 730),
        ("فحص تسربات منظومة نقل الحركة", None, None, 30),
    ]),
    ("الفرامل", [
        ("فحص تيل أو بطانات الفرامل", None, None, 30),
        ("فحص أقراص أو طبول الفرامل", None, None, 90),
        ("فحص مستوى زيت الفرامل", None, None, 30),
        ("استبدال زيت الفرامل", None, None, 730),
        ("فحص أنابيب وخراطيم الفرامل", None, None, 30),
        ("فحص أسطوانات وكليبرات الفرامل", None, None, 180),
        ("فحص فرامل التوقف", None, None, 90),
        ("اختبار كفاءة الفرامل", None, None, 180),
        ("نزف دائرة الفرامل", None, None, 730),
        ("فحص نظام ABS", None, None, 180),
    ]),
    ("التوجيه", [
        ("فحص خلوص نظام التوجيه", None, None, 90),
        ("فحص أذرع ووصلات التوجيه", None, None, 90),
        ("فحص المفاصل الكروية", None, None, 90),
        ("فحص مستوى زيت التوجيه", None, None, 30),
        ("فحص مضخة التوجيه", 30000, 750, None),
        ("ضبط زوايا العجلات", 20000, 500, 365),
        ("فحص تسربات نظام التوجيه", None, None, 30),
    ]),
    ("التعليق", [
        ("فحص ممتصات الصدمات", None, None, 90),
        ("فحص النوابض", None, None, 180),
        ("فحص أذرع التعليق", None, None, 90),
        ("فحص الجلب المطاطية", None, None, 90),
        ("فحص المفاصل", None, None, 90),
        ("فحص قضيب الموازن ووصلاته", None, None, 90),
        ("فحص قواعد التعليق", None, None, 180),
    ]),
    ("الإطارات والعجلات", [
        ("فحص ضغط الإطارات", None, None, 7),
        ("فحص حالة ومداس الإطارات", None, None, 30),
        ("فحص التآكل غير المنتظم", None, None, 30),
        ("فحص التشققات والأضرار", None, None, 30),
        ("تدوير الإطارات", 10000, 250, None),
        ("ترصيص العجلات", 20000, 500, 365),
        ("فحص صواميل العجلات وشدها", None, None, 30),
        ("فحص العجلة الاحتياطية", None, None, 90),
        ("فحص نظام مراقبة ضغط الإطارات", None, None, 90),
    ]),
    ("نظام الوقود", [
        ("فحص مستوى الوقود والخزان", None, None, 30),
        ("فحص خطوط وخراطيم الوقود", None, None, 90),
        ("فحص مضخة الوقود", 40000, 1000, None),
        ("استبدال مرشح الوقود", 20000, 500, None),
        ("فحص الحاقنات", 40000, 1000, None),
        ("فحص ضغط الوقود", 40000, 1000, None),
        ("فحص تسربات الوقود", None, None, 30),
    ]),
    ("العادم والانبعاثات", [
        ("فحص أنابيب العادم", None, None, 90),
        ("فحص كاتم الصوت", None, None, 180),
        ("فحص المحول الحفاز", 40000, 1000, None),
        ("فحص نظام EGR", 40000, 1000, None),
        ("فحص وتنظيف DPF عند الحاجة", 40000, 1000, None),
        ("فحص حساسات الانبعاثات", 40000, 1000, None),
        ("فحص تسربات العادم", None, None, 30),
    ]),
    ("التكييف والتدفئة", [
        ("فحص أداء التكييف والتدفئة", None, None, 180),
        ("فحص تسرب وسيط التبريد", None, None, 180),
        ("فحص ضاغط التكييف", 30000, 750, None),
        ("فحص المكثف والمبخر", None, None, 365),
        ("استبدال فلتر المقصورة", 20000, 500, 365),
        ("فحص مروحة التهوية", None, None, 180),
    ]),
    ("الهيكل والمقصورة", [
        ("فحص الهيكل والتآكل والصدأ", None, None, 180),
        ("فحص الأبواب والمفصلات والأقفال", None, None, 90),
        ("فحص الزجاج والمرايا", None, None, 30),
        ("فحص المقاعد", None, None, 180),
        ("فحص المساحات ورشاشات الزجاج", None, None, 30),
        ("تنظيف وفحص المقصورة", None, None, 30),
    ]),
    ("السلامة", [
        ("فحص أحزمة الأمان", None, None, 90),
        ("فحص الوسائد الهوائية ونظام SRS", None, None, 180),
        ("فحص طفاية الحريق", None, None, 30),
        ("فحص مثلث التحذير ومعدات الطوارئ", None, None, 90),
        ("فحص صندوق الإسعاف", None, None, 90),
        ("فحص إشارات وتحذيرات السلامة", None, None, 30),
    ]),
    ("السوائل والتشحيم", [
        ("فحص مستويات السوائل", None, None, 30),
        ("فحص زيت المحرك", None, None, 7),
        ("فحص زيوت ناقل الحركة والتفاضل", None, None, 90),
        ("فحص زيت الفرامل", None, None, 30),
        ("فحص سائل التوجيه", None, None, 30),
        ("فحص سائل المساحات", None, None, 30),
        ("تشحيم نقاط التشحيم", 10000, 250, 180),
        ("فحص جميع التسربات", None, None, 30),
    ]),
    ("الفحص العام والتشخيص", [
        ("فحص بصري شامل للعتاد", None, None, 30),
        ("فحص الأصوات غير الطبيعية", None, None, 30),
        ("فحص الاهتزازات غير الطبيعية", None, None, 30),
        ("فحص درجات حرارة التشغيل", None, None, 90),
        ("قراءة رموز الأعطال الإلكترونية", None, None, 90),
        ("اختبار التشغيل بعد الصيانة", None, None, 30),
        ("اختبار الطريق عند الحاجة", None, None, 180),
    ]),
]


def upgrade() -> None:
    bind = op.get_bind()
    groups = sa.table(
        "maintenance_operation_groups",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    operations = sa.table(
        "maintenance_operations",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("interval_km", sa.Numeric),
        sa.column("interval_hours", sa.Numeric),
        sa.column("interval_days", sa.Integer),
        sa.column("warning_km", sa.Numeric),
        sa.column("warning_days", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("description", sa.Text),
        sa.column("group_id", sa.Integer),
    )

    for sort_order, (group_name, items) in enumerate(GROUPS, start=1):
        row = bind.execute(
            sa.select(groups.c.id).where(groups.c.name == group_name)
        ).first()
        if row:
            group_id = row[0]
        else:
            group_id = bind.execute(
                groups.insert().values(
                    name=group_name,
                    sort_order=sort_order,
                ).returning(groups.c.id)
            ).scalar_one()

        for name, km, hours, days in items:
            exists = bind.execute(
                sa.select(operations.c.id).where(
                    operations.c.name == name,
                    operations.c.group_id == group_id,
                )
            ).first()
            if exists:
                continue

            warning_km = km * 0.1 if km is not None else None
            warning_days = max(1, days // 5) if days is not None else None
            bind.execute(
                operations.insert().values(
                    name=name,
                    interval_km=km,
                    interval_hours=hours,
                    interval_days=days,
                    warning_km=warning_km,
                    warning_days=warning_days,
                    is_active=True,
                    description="عملية قياسية قابلة للتعديل؛ يحدد الفاصل النهائي حسب دليل الشركة المصنعة والطراز وظروف التشغيل.",
                    group_id=group_id,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    groups = sa.table(
        "maintenance_operation_groups",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
    )
    operations = sa.table(
        "maintenance_operations",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("group_id", sa.Integer),
    )

    names = [name for name, _ in GROUPS]
    rows = bind.execute(sa.select(groups.c.id).where(groups.c.name.in_(names))).all()
    group_ids = [row[0] for row in rows]
    if group_ids:
        bind.execute(operations.delete().where(operations.c.group_id.in_(group_ids)))
        bind.execute(groups.delete().where(groups.c.id.in_(group_ids)))
