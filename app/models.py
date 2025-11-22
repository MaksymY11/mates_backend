from sqlalchemy import JSON, Table, Column, Integer, String, DateTime, MetaData

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True),
    Column("password", String),
    Column("avatar_url", String, nullable=True),
    Column("name", String, nullable=True),
    Column("age", Integer, nullable=True),
    Column("state", String, nullable=True),
    Column("city", String, nullable=True),
    Column("budget", Integer, nullable=True),
    Column("move_in_date", DateTime, nullable=True),
    Column("bio", String, nullable=True),
    Column("lifestyle", JSON, nullable=True),
    Column("activities", JSON, nullable=True),
    Column("prefs", JSON, nullable=True),
)

refresh_tokens = Table(
    "refresh_tokens",
    metadata,
    Column("token", String, primary_key=True, index=True),
    Column("user_email", String, index=True),
    Column("expires_at", DateTime),
)
