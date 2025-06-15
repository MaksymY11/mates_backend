from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.database import database
from app.models import users
from passlib.context import CryptContext
from jose import jwt
import os
from pydantic import BaseModel

class UserRegister(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="loginUser")

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
async def login_user(user: UserLogin):
    query = users.select().where(users.c.email == user.email)
    db_user = await database.fetch_one(query)
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Generate a JWT token
    token = jwt.encode({"email": db_user["email"]}, JWT_SECRET, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
async def get_me(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return {"email": payload["email"]}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
