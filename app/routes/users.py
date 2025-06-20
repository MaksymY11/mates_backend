from fastapi import Depends, APIRouter, HTTPException, Response, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.database import database
from app.models import users, refresh_tokens
from passlib.context import CryptContext
from app.auth import (
    create_access_token,
    verify_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
)
from pydantic import BaseModel
import os
import secrets
from datetime import datetime, timedelta

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

    # Generate tokens with expiration
    access_token = create_access_token(
        {"email": db_user["email"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    r_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await database.execute(
        refresh_tokens.insert().values(
            token=r_token,
            user_email=db_user["email"],
            expires_at=expires_at,
        )
    )
    response.set_cookie(
        "refresh_token",
        r_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refreshToken")
async def refresh_token(request: Request, response: Response):
    r_token = request.cookies.get("refresh_token")
    if not r_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    record = await database.fetch_one(
        refresh_tokens.select().where(refresh_tokens.c.token == r_token)
    )
    if not record or record["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    await database.execute(
        refresh_tokens.delete().where(refresh_tokens.c.token == r_token)
    )
    new_r_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await database.execute(
        refresh_tokens.insert().values(
            token=new_r_token,
            user_email=record["user_email"],
            expires_at=expires_at,
        )
    )
    new_access_token = create_access_token({"email": record["user_email"]})
    response.set_cookie(
        "refresh_token",
        new_r_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    r_token = request.cookies.get("refresh_token")
    if r_token:
        await database.execute(
            refresh_tokens.delete().where(refresh_tokens.c.token == r_token)
        )
    response.delete_cookie("refresh_token")
    return {"detail": "logged out"}

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@router.get("/me")
async def get_me(payload: dict = Depends(get_current_user)):
    return {"email": payload["email"]}
    
if DEBUG_MODE:
    @router.get("/debug/users")
    async def debug_list_users(payload: dict = Depends(get_current_user)):
        rows = await database.fetch_all("SELECT id, email, password FROM users;")
        return [dict(row) for row in rows]
