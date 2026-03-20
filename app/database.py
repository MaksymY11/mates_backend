from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import MetaData
import os

ASYNC_DATABASE_URL = os.getenv("ASYNC_DATABASE_URL")
if not ASYNC_DATABASE_URL:
    raise RuntimeError("ASYNC_DATABASE_URL is not set. Please define it in your environment.")

# Create the engine
engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)

# Session factory, each request gets its own session
AssyncSessionLocal = sessionmaker(
    bind = engine,
    class_ = AsyncSession,
    expire_on_commit=False,
)

# Create metadata instance used by models & alembic
metadata = MetaData()

# Dependency for FastAPI routes
async def get_db():
    async with AssyncSessionLocal() as session:
        yield session
