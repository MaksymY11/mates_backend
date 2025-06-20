# Mates Backend — FastAPI Auth System 🔐🚀

Full backend for the Mates project using:

- FastAPI ⚡
- SQLite (dev DB)
- SQLAlchemy ORM
- Passlib (password hashing)
- JWT Authentication (secure token-based auth)
- Clean project structure

---

## 🗂️ Project Structure
app/
├── __init__.py
├── main.py          # FastAPI entry point
├── database.py      # DB connection
├── models.py        # DB models
├── schemas.py       # Pydantic schemas
├── crud.py          # DB operations
├── security.py      # Password hashing
├── auth.py          # JWT token logic
└── routes/
    ├── __init__.py
    └── users.py     # API routes
mates.db             # SQLite file
requirements.txt     # Dependencies

---

## ⚙️ Installation

### 1️⃣ Clone repo and create virtualenv

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate         # Windows
```

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
# If needed:
pip install fastapi uvicorn sqlalchemy databases aiosqlite passlib[bcrypt] python-jose[cryptography]
```

### 3️⃣ Set environment variables

Copy `.env.example` to `.env` and update the values:

```bash
cp .env.example .env
# Edit .env and set:
# DATABASE_URL=sqlite+aiosqlite:///./mates.db
# JWT_SECRET=supersecretkey
```

---

## 🚀 Run server locally

```bash
uvicorn app.main:app --reload
```

Server will be available at:
http://127.0.0.1:8000
Swagger API docs:
http://127.0.0.1:8000/docs

---

## 🔐 Auth Flow

### 1️⃣ Registration (No auth required)

`POST /registerUser`

```json
{
  "email": "test@example.com",
  "password": "yourpassword"
}
```

### 2️⃣ Login (No auth required)

`POST /loginUser`

Returns:

```json
{
  "access_token": "<JWT_TOKEN>",
  "token_type": "bearer"
}
```

### ♻️ Refresh token

`POST /refreshToken`

Send request with the `refresh_token` cookie returned during login. Returns a new access token and rotates the refresh token cookie.

### 3️⃣ Protected routes

Click 🔒 Authorize button in Swagger

Paste token as:

```
Bearer <JWT_TOKEN>
```

Now call:

`GET /me`

Returns:

```json
{
  "email": "<email>"
}
```
