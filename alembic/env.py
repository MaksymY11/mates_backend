from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import os
import re

# Load metadata from your models
from app.models import metadata

# Alembic Config
DATABASE_URL = os.getenv("DATABASE_URL")    # Use DATABASE_URL from environment
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    alembic_url = re.sub(r'^postgresql\+asyncpg://', 'postgresql://', DATABASE_URL)
else:
    alembic_url = DATABASE_URL
config = context.config
config.set_main_option("sqlalchemy.url", alembic_url)
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

async def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: context.configure(
                connection=conn,
                target_metadata=target_metadata
            )
        )
        await connection.run_sync(lambda conn: context.run_migrations())

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())
