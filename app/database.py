from sqlalchemy import create_engine
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Detect if using SQLite (for local dev)
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)