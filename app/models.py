from sqlalchemy import JSON, Boolean, Date, Table, Column, Integer, String, Float, DateTime, MetaData, ForeignKey, UniqueConstraint
from datetime import datetime

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
    Column("location_preference", String, nullable=False, server_default="same_city"),
    Column("email_verified", Boolean, nullable=False, server_default="false"),
)

refresh_tokens = Table(
    "refresh_tokens",
    metadata,
    Column("token", String, primary_key=True, index=True),
    Column("user_email", String, ForeignKey("users.email", ondelete="CASCADE"), index=True),
    Column("expires_at", DateTime),
)

verification_codes = Table(
    "verification_codes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_email", String, nullable=False, index=True),
    Column("code_hash", String, nullable=False),
    Column("purpose", String, nullable=False), # email verification or password reset
    Column("expires_at", DateTime, nullable=False),
    Column("used", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime, nullable=False),
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

interests = Table(
    "interests",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("from_user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("to_user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("from_user_id", "to_user_id", name="uq_interest_pair"),
)

quick_pick_questions = Table(
    "quick_pick_questions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("prompt", String, nullable=False),
    Column("option_a", String, nullable=False),
    Column("option_b", String, nullable=False),
    Column("category", String, nullable=False),
)

quick_pick_sessions = Table(
    "quick_pick_sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_a_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("user_b_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("status", String, nullable=False, server_default="pending_both"),
    Column("questions", JSON, nullable=False),
    Column("results_viewed_by", JSON, nullable=False, server_default="[]"),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("user_a_id", "user_b_id", name="uq_quickpick_session_pair"),
)

quick_pick_answers = Table(
    "quick_pick_answers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("quick_pick_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("question_index", Integer, nullable=False),
    Column("selected_option", String, nullable=False),
    Column("answered_at", DateTime, nullable=False),
    UniqueConstraint("session_id", "user_id", "question_index", name="uq_quickpick_answer"),
)

households = Table(
    "households",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("created_by", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

household_members = Table(
    "household_members",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("household_id", Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
    Column("role", String, nullable=False),
    Column("joined_at", DateTime, nullable=False),
)

household_invites = Table(
    "household_invites",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("household_id", Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
    Column("inviter_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("invitee_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("status", String, nullable=False, server_default="pending"),
    Column("created_at", DateTime, nullable=False),
    UniqueConstraint("household_id", "invitee_id", name="uq_household_invitee"),
)

house_rules = Table(
    "house_rules",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("household_id", Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
    Column("text", String, nullable=False),
    Column("proposed_by", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("status", String, nullable=False, server_default="proposed"),
    Column("created_at", DateTime, nullable=False),
)

house_rule_votes = Table(
    "house_rule_votes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("rule_id", Integer, ForeignKey("house_rules.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("vote", Boolean, nullable=False),
    UniqueConstraint("rule_id", "user_id", name="uq_rule_user_vote"),
)

conversations = Table(
    "conversations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("type", String, nullable=False),  # "dm" or "group"
    Column("household_id", Integer, ForeignKey("households.id", ondelete="CASCADE"), nullable=True, unique=True),
    Column("created_at", DateTime, nullable=False),
)

conversation_participants = Table(
    "conversation_participants",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("conversation_id", Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("joined_at", DateTime, nullable=False),
    Column("last_read_at", DateTime, nullable=True),
    UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("conversation_id", Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
    Column("sender_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("body", String, nullable=False),
    Column("created_at", DateTime, nullable=False, index=True),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("event_type", String, nullable=False),
    Column("actor_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    Column("title", String, nullable=False),
    Column("body", String, nullable=False),
    Column("data", JSON, nullable=True),
    Column("read", Boolean, default=False, server_default="false"),
    Column("created_at", DateTime, default=datetime.utcnow, index=True),
)

device_tokens = Table(
    "device_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("fcm_token", String, nullable=False, unique=True),
    Column("platform", String, nullable=False),  # "android", "ios", "web"
    Column("created_at", DateTime, nullable=False),
)
