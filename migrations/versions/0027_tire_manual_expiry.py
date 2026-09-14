"""track manually entered tire expiry dates

revision: 0027
"""
import calendar
from datetime import date

from alembic import op
import sqlalchemy as sa

revision = "0027_tire_manual_expiry"
down_revision = "0026_tire_movement_datetime"
branch_labels = None
depends_on = None


def _add_years(value, years):
    day = min(value.day, calendar.monthrange(value.year + years, value.month)[1])
    return date(value.year + years, value.month, day)


def upgrade():
    op.add_column("tires", sa.Column("expiry_date_manual", sa.Boolean(), nullable=False, server_default=sa.false()))
    bind = op.get_bind()
    setting = bind.execute(sa.text("SELECT validity_years FROM tire_system_settings WHERE id = 1")).scalar()
    years = int(setting or 3)
    rows = bind.execute(sa.text("SELECT id, manufacture_date, receipt_date, expiry_date FROM tires")).mappings().all()
    for row in rows:
        base_raw = row["manufacture_date"] or row["receipt_date"]
        expiry_raw = row["expiry_date"]
        if not base_raw or not expiry_raw:
            continue
        base = base_raw if isinstance(base_raw, date) else date.fromisoformat(str(base_raw)[:10])
        expiry = expiry_raw if isinstance(expiry_raw, date) else date.fromisoformat(str(expiry_raw)[:10])
        if expiry != _add_years(base, years):
            bind.execute(sa.text("UPDATE tires SET expiry_date_manual = 1 WHERE id = :id"), {"id": row["id"]})


def downgrade():
    op.drop_column("tires", "expiry_date_manual")
