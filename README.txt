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
├── init.py
├── main.py # FastAPI entry point
├── database.py # DB connection
├── models.py # DB models
├── schemas.py # Pydantic schemas
├── crud.py # DB operations
├── security.py # Password hashing
├── auth.py # JWT token logic
└── routes/
├── init.py
└── users.py # API routes
mates.db # SQLite file
requirements.txt # Dependencies

---

## ⚙️ Installation

### 1️⃣ Clone repo and create virtualenv

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
If needed:
```bash
pip install fastapi uvicorn sqlalchemy databases aiosqlite passlib[bcrypt] python-jose[cryptography]

---

## 🚀 Run server locally

uvicorn app.main:app --reload
Server will be available at:
http://127.0.0.1:8000
Swagger API docs:
http://127.0.0.1:8000/docs

---

##🔐 Auth Flow

### 1️⃣ Registration (No auth required)

POST /registerUser

{
  "email": "test@example.com",
  "password": "yourpassword"
}

### 2️⃣ Login (No auth required)

POST /loginUser
Returns:
{
  "access_token": "<JWT_TOKEN>",
  "token_type": "bearer"
}

### 3️⃣ Protected routes

Click 🔒 Authorize button in Swagger

Paste token as:
Bearer <JWT_TOKEN>
Now call:

GET /protected

Returns:

{
  "message": "Welcome, <email>!"
}