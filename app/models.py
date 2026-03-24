from sqlalchemy import JSON, Boolean, Date, Table, Column, Integer, String, Float, DateTime, MetaData, ForeignKey, UniqueConstraint

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

scenarios = Table(
    "scenarios",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("prompt", String, nullable=False),
    Column("options", JSON, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)

scenario_responses = Table(
    "scenario_responses",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("scenario_id", Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
    Column("selected_option", String, nullable=False),
    Column("answered_at", DateTime, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
    UniqueConstraint("user_id", "scenario_id", name="uq_user_scenario"),
)

neighborhoods = Table(
    "neighborhoods",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("centroid", JSON, nullable=True),
    Column("vibe_description", String, nullable=True),
    Column("updated_at", DateTime, nullable=False),
)

neighborhood_members = Table(
    "neighborhood_members",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
    Column("neighborhood_id", Integer, ForeignKey("neighborhoods.id", ondelete="CASCADE"), nullable=False),
    Column("similarity_score", Float, nullable=True),
    Column("assigned_at", DateTime, nullable=False),
)

daily_scenario_assignments = Table(
    "daily_scenario_assignments",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("scenario_id", Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
    Column("assigned_date", Date, nullable=False),
    Column("completed", Boolean, nullable=False, default=False),
)
