from fastapi import Depends, APIRouter, HTTPException, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.database import database
from app.models import users
from passlib.context import CryptContext
from jose import jwt
from app.auth import SECRET_KEY
from pydantic import BaseModel
import os
import secrets

# Determine if debug endpoints should be available
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

class UserRegister(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()
refresh_tokens = {}

@router.post("/registerUser")
async def register_user(user: UserRegister):
    # user.email and user.password (dot notation)
    hashed_password = pwd_context.hash(user.password)
    query = users.insert().values(email=user.email, password=hashed_password)
    try:
        await database.execute(query)
        return {"msg": "User created"}
    except Exception:
        raise HTTPException(status_code=400, detail="User already exists")

@router.post("/loginUser")
async def login_user(user: UserLogin, response: Response):
    query = users.select().where(users.c.email == user.email)
    db_user = await database.fetch_one(query)
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Generate access and refresh tokens
    token = jwt.encode({"email": db_user["email"]}, SECRET_KEY, algorithm="HS256")
    r_token = secrets.token_urlsafe(32)
    refresh_tokens[r_token] = db_user["email"]
    response.set_cookie("refresh_token", r_token, httponly=True)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/refreshToken")
async def refresh_token(request: Request, response: Response):
    r_token = request.cookies.get("refresh_token")
    if not r_token or r_token not in refresh_tokens:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    email = refresh_tokens.pop(r_token)
    new_access_token = jwt.encode({"email": email}, SECRET_KEY, algorithm="HS256")
    new_r_token = secrets.token_urlsafe(32)
    refresh_tokens[new_r_token] = email
    response.set_cookie("refresh_token", new_r_token, httponly=True)
    return {"access_token": new_access_token, "token_type": "bearer"}

@router.get("/me")
async def get_me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return {"email": payload["email"]}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    
if DEBUG_MODE:
    @router.get("/debug/users")
    async def debug_list_users():
        rows = await database.fetch_all("SELECT id, email, password FROM users;")
        return [dict(row) for row in rows]
