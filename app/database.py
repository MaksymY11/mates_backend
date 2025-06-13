from sqlalchemy import MetaData, create_engine
from databases import Database
import os

DATABASE_URL = os.getenv("DATABASE_URL")

# Conditional connect args for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Create the engine
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Create metadata instance
metadata = MetaData()

# Create async database instance for use in startup/shutdown
database = Database(DATABASE_URL)
