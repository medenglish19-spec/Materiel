"""
database/base.py
-----------------
Base واحد مشترك لكل موديلات النظام (بغض النظر عن الوحدة). هذا ما يسمح لـ
SQLAlchemy يعرف كل الجداول عند إنشاء قاعدة البيانات، ويسمح بعمل علاقات
(ForeignKey) بين وحدات مختلفة عند الحاجة (مثال: maintenance يشير إلى
equipment) دون كسر استقلالية الوحدات على مستوى الكود.

قاعدة مهمة: لا تُنشئ Base منفصل لكل وحدة. وحدة واحدة = Base واحد للمشروع كله.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

# كل مفتاح أجنبي يأخذ اسمًا ثابتًا. بدون هذا تُنشئ create_all() مفاتيح بلا أسماء،
# فتختلف القاعدة المبنية من الموديلات عن القاعدة المبنية بالـ migrations، وتفشل
# batch_alter_table() عند نسخ قيد بلا اسم -- وهو ما أوقف الإقلاع على قواعد موجودة.
# التمديد ينتج الأسماء نفسها التي تكتبها migrations/versions، فتوافق القاعدة
# الجديدة المهاجرة.
#
# ملاحظة: هذا القاموس يستبدل افتراضات SQLAlchemy ولا يضيف إليها. المفتاحان
# الآخران ("uq" و"ck" و"pk") لا يُذكران عمدًا: كل قيد فريد وشرط في هذا المشروع
# مسمّى صراحةً في __table_args__، وإضافتهما هنا تعيد تسمية ما هو مسمّى أصلًا
# ("ck_%(table_name)s_%(constraint_name)s" ينتج ck_<table>_ck_<name> مزدوجًا).
# و"ix" يجب أن يبقى: فهارس index=True بلا اسم تعتمد عليه، وحذفه يجعل
# create_all() يفشل بـ assert name is not None.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))
