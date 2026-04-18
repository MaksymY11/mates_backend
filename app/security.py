from passlib.context import CryptContext
from zxcvbn import zxcvbn
from fastapi import HTTPException
import random
from datetime import datetime, timezone

MIN_PASSWORD_SCORE = 3
CODE_EXPIRY_MIN = 10

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def validate_password_strength(password: str) -> None:
    """Raise HTTPException(400) if password is too weak per zxcvbn. Score must be >= 3."""

    result = zxcvbn(password)
    if result["score"] < MIN_PASSWORD_SCORE:
        warning = result["feedback"]["warning"]
        suggestions = result["feedback"]["suggestions"]
        detail = warning or (suggestions[0] if suggestions else "Password too weak")
        raise HTTPException(status_code=400, detail=detail)
    
def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"