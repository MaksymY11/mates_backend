from sqlalchemy import JSON, Table, Column, Integer, String, Float, DateTime, MetaData, ForeignKey, UniqueConstraint

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
    Column("user_email", String, ForeignKey("users.email", ondelete="CASCADE"), index=True),
    Column("expires_at", DateTime),
)

furniture_catalog = Table(
    "furniture_catalog",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("zone", String, nullable=False),
    Column("category", String, nullable=False),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("icon_name", String, nullable=True),
    Column("constraint_group", String, nullable=True),
    Column("preference_weights", JSON, nullable=True),
)

room_style_presets = Table(
    "room_style_presets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("zone", String, nullable=False),
    Column("name", String, nullable=False),
    Column("description", String, nullable=True),
    Column("furniture_ids", JSON, nullable=True),
)

apartments = Table(
    "apartments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

apartment_items = Table(
    "apartment_items",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("apartment_id", Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False),
    Column("furniture_id", Integer, ForeignKey("furniture_catalog.id", ondelete="CASCADE"), nullable=False),
    Column("zone", String, nullable=False),
    Column("position_x", Float, nullable=False, default=0),
    Column("position_y", Float, nullable=False, default=0),
)

preference_profiles = Table(
    "preference_profiles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
    Column("weights", JSON, nullable=True),
    Column("vibe_labels", JSON, nullable=True),
    Column("updated_at", DateTime, nullable=False),
)
