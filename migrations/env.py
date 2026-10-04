import logging
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import settings
from app.database.base import Base
from app.database import model_registry  # noqa: F401

config = context.config
# One log for everything. fileConfig() rewrites the root logger and sets
# disabled=True on every logger that already exists, so running it here silenced
# the app: every message logged after that -- including logger.exception() for a
# failed migration -- went nowhere, and alembic's own messages landed in their
# separate stream instead of logs/app.log.
#
# So: when the app has already configured logging, leave it alone; when nobody
# has (the `alembic` CLI), configure it the same way instead. alembic.ini asks
# for the alembic logger at INFO, so keep that regardless of the app's level --
# migrations are only interesting when you can see which ones ran.
if config.config_file_name is not None and not logging.getLogger().handlers:
    import atexit

    from app.core.logging import configure_logging, shutdown_logging

    configure_logging()
    logging.getLogger("alembic").setLevel(logging.INFO)
    # The app's listener drains on a background thread. Under the CLI nothing
    # else does, so the last records -- the ones a failed migration is made of --
    # were still queued when the process exited. atexit drains them.
    atexit.register(shutdown_logging)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True, compare_server_default=True, render_as_batch=settings.DATABASE_URL.startswith("sqlite"))
    with context.begin_transaction(): context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    # Alembic always migrates the database the *app* is configured for, so this
    # deliberately wins over both alembic.ini and anything a caller put in
    # Config.set_main_option("sqlalchemy.url", ...). To migrate a different
    # database, change settings.DATABASE_URL (the DATABASE_URL environment
    # variable) -- setting it on the Config silently does nothing.
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connect_args = {"timeout": 5} if settings.DATABASE_URL.startswith("sqlite") else {}
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool, connect_args=connect_args)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, compare_server_default=True, render_as_batch=settings.DATABASE_URL.startswith("sqlite"))
        with context.begin_transaction(): context.run_migrations()


if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
