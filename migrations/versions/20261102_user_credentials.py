"""Allow non-empty user names and passwords without arbitrary length rules."""

from alembic import op


revision = "20261102_user_credentials"
down_revision = "20261101_equipment_image"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS users_username_nonempty_insert
            BEFORE INSERT ON users
            WHEN NEW.username = ''
            BEGIN
                SELECT RAISE(ABORT, 'username must not be empty');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS users_username_nonempty_update
            BEFORE UPDATE OF username ON users
            WHEN NEW.username = ''
            BEGIN
                SELECT RAISE(ABORT, 'username must not be empty');
            END
            """
        )
    else:
        op.create_check_constraint(
            "ck_users_username_nonempty", "users", "length(username) > 0"
        )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS users_username_nonempty_insert")
        op.execute("DROP TRIGGER IF EXISTS users_username_nonempty_update")
    else:
        op.drop_constraint("ck_users_username_nonempty", "users", type_="check")
