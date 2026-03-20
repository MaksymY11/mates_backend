# Mates Backend — FastAPI REST API

Backend for the Mates roommate-matching app.

- **Framework:** FastAPI
- **Database:** PostgreSQL (Neon) via SQLAlchemy async + asyncpg
- **Auth:** JWT access tokens + HTTP-only refresh token cookies
- **Storage:** Local static file serving for avatars (Pillow validation + thumbnail generation)
- **Migrations:** Alembic
- **Deployed on:** Render

---

## Project Structure

```
app/
├── __init__.py
├── main.py          # FastAPI entry point, CORS, lifespan
├── database.py      # Async SQLAlchemy engine and session factory
├── models.py        # SQLAlchemy table definitions (users, refresh_tokens)
├── schemas.py       # Pydantic schemas
├── crud.py          # DB operations (legacy, routes use direct queries)
├── security.py      # Password hashing
├── auth.py          # JWT token creation and verification
└── routes/
    ├── __init__.py
    └── users.py     # All API routes

alembic/             # Database migrations
static/avatars/      # Uploaded avatar images (local)
requirements.txt
.env.example
```

---

## Data Model

### users

| Column       | Type     | Notes                  |
| ------------ | -------- | ---------------------- |
| id           | Integer  | Primary key            |
| email        | String   | Unique, indexed        |
| password     | String   | bcrypt hash            |
| avatar_url   | String   | URL to uploaded avatar |
| name         | String   | Display name           |
| age          | Integer  |                        |
| state        | String   |                        |
| city         | String   |                        |
| budget       | Integer  | Monthly budget         |
| move_in_date | DateTime |                        |
| bio          | String   |                        |
| lifestyle    | JSON     | Living habits          |
| activities   | JSON     | Interests              |
| prefs        | JSON     | Roommate preferences   |

### refresh_tokens

| Column     | Type     | Notes                |
| ---------- | -------- | -------------------- |
| token      | String   | Primary key, indexed |
| user_email | String   | Indexed              |
| expires_at | DateTime |                      |

---

## API Endpoints

### Auth

| Method | Endpoint        | Auth   | Description                                       |
| ------ | --------------- | ------ | ------------------------------------------------- |
| POST   | `/registerUser` | No     | Register and auto-login, returns access token     |
| POST   | `/loginUser`    | No     | Login, returns access token + sets refresh cookie |
| POST   | `/refreshToken` | Cookie | Rotate refresh token, returns new access token    |
| POST   | `/logout`       | Cookie | Invalidate refresh token, clear cookie            |

### Profile

| Method | Endpoint        | Auth   | Description                                 |
| ------ | --------------- | ------ | ------------------------------------------- |
| GET    | `/me`           | Bearer | Get current user profile (no password)      |
| POST   | `/updateUser`   | Bearer | Update profile fields                       |
| POST   | `/uploadAvatar` | Bearer | Upload avatar image (max 5MB, JPEG/PNG/GIF) |

### Debug (only when `DEBUG=true`)

| Method | Endpoint       | Auth   | Description                          |
| ------ | -------------- | ------ | ------------------------------------ |
| GET    | `/debug/users` | Bearer | List all users with hashed passwords |

---

## Auth Flow

### Registration

```
POST /registerUser → { access_token, token_type }
                    + sets refresh_token HTTP-only cookie
```

### Login

```
POST /loginUser → { access_token, token_type }
                + sets refresh_token HTTP-only cookie
```

### Authenticated requests

```
Authorization: Bearer <access_token>
```

### Token refresh

```
POST /refreshToken (sends refresh_token cookie automatically)
→ { access_token, token_type } + rotated refresh_token cookie
```

### Logout

```
POST /logout → clears refresh_token cookie, invalidates token in DB
```

**Note:** Access tokens remain valid until expiry (default 30 min) even after logout. This is a known JWT tradeoff — the refresh token is immediately invalidated so no new access tokens can be issued.

---

## Installation

### 1. Clone and create virtualenv

```bash
git clone https://github.com/MaksymY11/mates_backend.git
cd mates_backend
python -m venv venv

# Mac/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
DATABASE_URL=postgresql://user:password@host.neon.tech/dbname?sslmode=require
ASYNC_DATABASE_URL=postgresql+asyncpg://user:password@host.neon.tech/dbname?ssl=require
JWT_SECRET=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_MINUTES=43200
```

### 4. Run migrations

```bash
alembic upgrade head
```

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

Server: `http://127.0.0.1:8000`
Swagger docs: `http://127.0.0.1:8000/docs`

---

## Deployment (Render)

**Start command:**

```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 10000
```

Alembic runs migrations automatically on every deploy before the server starts.

**Required environment variables on Render:**

- `DATABASE_URL` — PostgreSQL URL with `postgresql://` prefix (used by Alembic)
- `ASYNC_DATABASE_URL` — same database with `postgresql+asyncpg://` prefix (used by app)
- `JWT_SECRET` — secret key for signing JWT tokens
- `ACCESS_TOKEN_EXPIRE_MINUTES` — access token lifetime in minutes
- `REFRESH_TOKEN_EXPIRE_MINUTES` — refresh token lifetime in minutes
- `BASE_URL` — public URL of the server (e.g. `https://mates-backend-dxma.onrender.com`) for building avatar URLs

---

## Avatar Upload

- Accepted formats: JPEG, PNG, GIF
- Max file size: 5MB
- Pillow validates actual image content (rejects spoofed file types)
- A 200x200 thumbnail is generated alongside each upload
- Previous avatar is automatically deleted when a new one is uploaded
- Files served from `/static/avatars/`

**Note:** Render's filesystem resets on each deploy. For production persistence, avatar storage should be migrated to an object store (S3 or similar).

---

## Environment Variables Reference

| Variable                       | Required | Description                             |
| ------------------------------ | -------- | --------------------------------------- |
| `DATABASE_URL`                 | Yes      | Sync PostgreSQL URL for Alembic         |
| `ASYNC_DATABASE_URL`           | Yes      | Async PostgreSQL URL for app queries    |
| `JWT_SECRET`                   | Yes      | JWT signing secret                      |
| `ACCESS_TOKEN_EXPIRE_MINUTES`  | No       | Default: 30                             |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | No       | Default: 43200 (30 days)                |
| `BASE_URL`                     | No       | Public server URL for avatar URLs       |
| `DEBUG`                        | No       | Set to `true` to enable debug endpoints |
