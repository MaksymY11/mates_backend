from sqlalchemy import Table, Column, Integer, String
from .database import metadata

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True),
    Column("password", String),
)
