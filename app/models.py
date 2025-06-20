from sqlalchemy import Table, Column, Integer, String, DateTime, MetaData

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True),
    Column("password", String),
)

refresh_tokens = Table(
    "refresh_tokens",
    metadata,
    Column("token", String, primary_key=True, index=True),
    Column("user_email", String, index=True),
    Column("expires_at", DateTime),
)
