"""allow a free-text spare part name on request items

المرجع: `spare_part_request_items.spare_part_id` كان `NOT NULL` مع مفتاح أجنبي
`RESTRICT` على `spare_parts.id`، فلا يمكن حفظ بند باسم حرّ إطلاقاً بدون تخزين
NULL في هذا العمود. لذلك يعدّل هذا الترحيل العمود ليصبح اختيارياً، ويضيف عمود
`spare_part_name` لتخزين الاسم الحرّ. لا يُحذف أي بيانات ولا يتغيّر أي سجل قائم:
البنود المرتبطة بالمكتبة تبقى كما هي (معرّفها واسمها)، والبنود الحرّة الجديدة
تظهر في `spare_part_name`.
"""

from alembic import op
import sqlalchemy as sa

revision = "free_text_spare_part_names"
down_revision = "add_received_date_spare_part_items"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "spare_part_request_items",
        sa.Column("spare_part_name", sa.String(length=160), nullable=True),
    )
    with op.batch_alter_table("spare_part_request_items", recreate="auto") as batch_op:
        batch_op.alter_column(
            "spare_part_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade():
    # بند بلا معرّف قطعة لا يمكن تمثيله في عمود NOT NULL: يُحذف قبل إعادة
    # القيد. البيانات المرتبطة بالمكتبة لا تُمَس.
    op.execute("DELETE FROM spare_part_request_items WHERE spare_part_id IS NULL")
    with op.batch_alter_table("spare_part_request_items", recreate="auto") as batch_op:
        batch_op.alter_column(
            "spare_part_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.drop_column("spare_part_request_items", "spare_part_name")
