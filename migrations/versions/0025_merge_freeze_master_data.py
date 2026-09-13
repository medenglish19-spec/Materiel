"""merge freeze master-data branch into the main migration line

revision: 0025_merge_freeze_master_data
"""

revision = "0025_merge_freeze_master_data"
down_revision = ("0024_battery_system_setting", "0014_freeze_equipment_master_data")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
