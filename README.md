# Mates Backend

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_async-D71F00)
![WebSocket](https://img.shields.io/badge/WebSocket-real--time-010101)
![Render](https://img.shields.io/badge/Deployed_on-Render-46E3B7?logo=render&logoColor=white)

Backend for Mates, a roommate-matching app built for college students. Instead of swiping or ranking, Mates groups users into neighborhoods based on how they furnish a virtual apartment, then lets them form households through shared activities and conversation.

> **License:** Source-available. See [LICENSE](LICENSE) for terms.

---

## Tech Stack

- **FastAPI** with async request handling
- **PostgreSQL** (Neon) via SQLAlchemy 2.0 async + asyncpg
- **Alembic** for database migrations
- **WebSocket** for real-time messaging (via Starlette)
- **JWT** two-token auth with HTTP-only refresh cookies
- **Pillow** for avatar validation and thumbnail generation
- **Pure Python** k-means clustering (no numpy dependency)

---

## Features

<details>
<summary><strong>Apartment System</strong> — virtual apartment as a personality questionnaire</summary>
<br>

Users build out a virtual apartment by placing furniture items from a seeded catalog. Each item carries hidden preference weights, so the apartment doubles as a personality questionnaire without feeling like one. Furniture is organized by zone (bedroom, kitchen, living room, bathroom) with constraint groups that prevent conflicting picks. Style presets let users furnish an entire zone in one action.
</details>

<details>
<summary><strong>Vibe Engine</strong> — real-time preference profiling from apartment choices</summary>
<br>

Every time a user places or removes a furniture item, the vibe engine recalculates their preference profile. It sums the weights across all placed items, normalizes them, and maps the result to human-readable labels like "Night Owl" or "Social Butterfly." Recalculation happens atomically within the same database transaction as the item mutation, so the profile is always consistent.
</details>

<details>
<summary><strong>Daily Scenarios</strong> — situational questions as profile conversation starters</summary>
<br>

Each day, users get a situational question ("Your roommate keeps leaving dishes in the sink...") with multiple-choice responses. These don't feed into the vibe engine. They exist purely as conversation starters that show up on profiles. Users can hold up to three active responses at a time; answering a fourth triggers a substitution flow where they pick which old answer to retire. Retired responses are soft-deleted rather than removed, preserving history.
</details>

<details>
<summary><strong>Discovery and Neighborhood Clustering</strong> — from-scratch k-means with lazy invalidation</summary>
<br>

A from-scratch k-means implementation clusters users into neighborhoods based on their normalized preference weights. Clustering runs lazily on a user's first Discovery visit, or when their assignment has gone stale (more than 24 hours old). Apartment mutations invalidate the user's neighborhood membership but don't trigger an immediate recluster, deferring the work to the next page load. A global asyncio lock with a double-check pattern prevents duplicate clustering runs during concurrent requests.

Similarity scores between users are calculated using normalized Euclidean distance rather than centroid comparison, giving more meaningful neighbor rankings. Location filtering (same city, same state, or anywhere) is applied at query time as a post-filter, keeping the clustering itself location-agnostic.
</details>

<details>
<summary><strong>Quick Picks</strong> — mutual interest detection and rapid-fire compatibility sessions</summary>
<br>

A mutual-interest system where users "wave" at each other. When both users have waved, the backend auto-generates a five-question rapid-fire session drawn from the seeded question pool. Session pairs are normalized (lower user ID always maps to `user_a`) so that A waving at B and B waving at A resolve to the same session row. Each user answers independently, and the session tracks completion status per side. Withdrawing interest performs a clean break, deleting both interest directions and the session.
</details>

<details>
<summary><strong>Households</strong> — group formation with invites, roles, and majority-vote house rules</summary>
<br>

Groups of two to four users who form a shared living unit. Creating a household requires the members to have completed a Quick Picks session with each other, ensuring groups grow from genuine connections rather than cold invites. The system handles role management (creator role auto-transfers to the earliest-joined member if the creator leaves), invite expiration (seven-day TTL, cleaned on fetch), and collaborative house rules with majority-based voting. For two-member households, rules require unanimity; for three or four members, simple majority wins. Proposers auto-vote yes. Accepted rules can be challenged through a removal proposal that resets all votes and starts a fresh count.
</details>

<details>
<summary><strong>Real-Time Messaging</strong> — WebSocket delivery with optimistic rendering and cursor pagination</summary>
<br>

WebSocket connections for live message delivery, typing indicators, and read receipts. The REST layer handles conversation creation, message history with cursor-based pagination (ordered by auto-increment ID to avoid clock skew), and read status tracking. DM creation requires a completed Quick Picks session. Household creation auto-generates a group conversation, and members are added or removed as they join or leave.

The server skips echoing messages back to the sender since the frontend renders them optimistically on send. The in-process ConnectionManager maps user IDs to active sockets, suitable for single-server deployment.
</details>

---

## Scale

- **17 tables** across auth, apartments, preferences, scenarios, neighborhoods, interests, sessions, households, and messaging
- **40+ endpoints** organized across 8 route modules
- **~4,400 lines** of route logic, plus standalone engines for vibe calculation and clustering
- **5 seed scripts** for populating furniture catalogs, scenario questions, trade-off prompts, and test users

---

## Project Structure

```
app/
├── main.py              # FastAPI entry, CORS, lifespan
├── models.py            # 17 SQLAlchemy table definitions
├── schemas.py           # Pydantic request/response models
├── database.py          # Async engine and session factory
├── deps.py              # Shared auth dependencies
├── auth.py              # JWT creation and verification
├── security.py          # Password hashing (bcrypt)
├── vibe_engine.py       # Weight summing, normalization, label mapping
├── clustering.py        # Pure Python k-means (no numpy)
├── seed_furniture.py    # Furniture catalog + style presets
├── seed_scenarios.py    # 23 daily scenario questions
├── seed_quickpicks.py   # 18 trade-off questions across 5 categories
├── seed_users.py        # 12 test users with apartments + responses
└── routes/
    ├── users.py         # Auth, profile, avatar upload
    ├── apartments.py    # Apartment CRUD, furniture placement
    ├── vibe.py          # Vibe profiles and comparison
    ├── scenarios.py     # Daily scenarios, answers, comparison
    ├── discovery.py     # Neighborhoods, neighbors, nearby exploration
    ├── quickpicks.py    # Mutual interest, sessions, results
    ├── households.py    # Group formation, invites, house rules, voting
    └── messaging.py     # WebSocket + REST conversations

alembic/                 # Database migrations
static/avatars/          # Uploaded images (local, ephemeral on Render)
```
