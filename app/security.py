from passlib.hash import bcrypt
from zxcvbn import zxcvbn
from fastapi import HTTPException
from datetime import datetime, timezone
import secrets
import string

MIN_PASSWORD_SCORE = 3
CODE_EXPIRY_MIN = 10

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.verify(plain, hashed)

def validate_password_strength(password: str) -> None:
    results = zxcvbn(password)

    if results["score"] < MIN_PASSWORD_SCORE:
        feedback = results["feedback"]
        if feedback["warning"]:
            detail = feedback["warning"]
        elif feedback["suggestions"]:
            detail = feedback["suggestions"][0]
        else:
            detail = "Create a stronger password. For example, use symbols."
        raise HTTPException(status_code=400, detail=detail)
        
def now() -> datetime:
    """
    - Gets current time in UTC format.
    - We strip timezone info because of the convention. Prod uses UTC without timezone info so if we decide to include it code will break.
    - We should really be using timezones, but this is a future fix that needs to be done to make the system timezone-aware. Needs schema migrations across several tables.
    """

    return datetime.now(timezone.utc).replace(tzinfo=None)

def generate_code() -> str:
    """
    - We use secrets instead of random because latter is used mainly for simulations, not for security.
    - secrets chooses random digit from string.digits 6 times using a for-loop.
    """

    code = ''.join(secrets.choice(string.digits) for _ in range(6))
    return code