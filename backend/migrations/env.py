"""Alembic environment — connects to the database using the app settings."""

import os
from logging.config import fileConfig

# Import all models so Alembic can detect schema changes
import app.models  # noqa: F401
from alembic import context
from app.config import get_settings
from app.database import Base
from sqlalchemy import engine_from_config, pool

config = context.config
settings = get_settings()

# Allow DATABASE_SYNC_URL env var to override alembic.ini URL
sync_url = settings.database_sync_url or os.getenv("DATABASE_SYNC_URL", "")
if sync_url:
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the database directly)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
