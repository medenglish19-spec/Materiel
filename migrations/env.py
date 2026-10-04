import logging
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.core.config import settings
from app.database.base import Base
from app.database import model_registry  # noqa: F401

config = context.config
# fileConfig() rewrites the root logger and sets disabled=True on every logger
# that already exists. The app configures logging itself before it migrates
# (app/core/logging.py: a QueueHandler on root, drained to stderr and app.log),
# so running fileConfig() here silences every later startup message -- including
# logger.exception() for a failed migration, which is how a broken migration used
# to end as a silent "exited early" with no traceback anywhere.
# Only configure logging here when nobody else has, i.e. under the `alembic` CLI.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True, compare_server_default=True, render_as_batch=settings.DATABASE_URL.startswith("sqlite"))
    with context.begin_transaction(): context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connect_args = {"timeout": 5} if settings.DATABASE_URL.startswith("sqlite") else {}
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool, connect_args=connect_args)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, compare_server_default=True, render_as_batch=settings.DATABASE_URL.startswith("sqlite"))
        with context.begin_transaction(): context.run_migrations()


if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
