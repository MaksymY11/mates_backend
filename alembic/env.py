from logging.config import fileConfig
import os
from sqlalchemy import create_engine, pool
from alembic import context
from app.models import metadata

# Alembic Config object
config = context.config

# Make Alembic use the same DB as your app, but in sync mode
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Set up logging
fileConfig(config.config_file_name)
target_metadata = metadata

def run_migrations_offline():
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode (connect to the DB)."""
    url = config.get_main_option("sqlalchemy.url")

    # if using SQLite in tests, strip out the async driver
    if url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite+aiosqlite://", "sqlite:///")

    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        future=True,
    )
    with engine.begin() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        context.run_migrations()

# pick the right mode
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
