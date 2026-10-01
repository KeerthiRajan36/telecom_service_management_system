"""Alembic environment: schema comes from the app's models, URL from DATABASE_URL."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.db.base_class import Base
from app.db.types import UTCDateTime

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Keep migrations independent of app code: render our custom type as a plain timezone-aware DateTime."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _opts():
    return dict(
        target_metadata=target_metadata,
        compare_type=True,
        render_item=render_item,
        render_as_batch=settings.DATABASE_URL.startswith("sqlite"),  # SQLite can't ALTER most things in place
    )


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, literal_binds=True, dialect_opts={"paramstyle": "named"}, **_opts())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, **_opts())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
