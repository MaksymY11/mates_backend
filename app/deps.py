from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth import verify_access_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import users
from app.database import get_db

bearer_scheme = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """
    - Decode the Bearer access token and return its payload (includes `email`). 
    - Raises 401 if invalid or expired. 
    - Does NOT check  email_verified - use require_verified_user for that.
    """
    
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

async def require_verified_user(
        payload: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
) -> int:
    """
    - Require a verified email. Extends get_current_user with an email_verified check.
    - Raises 403 is email is not verified.
    - Returns user's id for further use inside the callers.
    """
    
    result = await db.execute(
        select(users.c.email_verified, users.c.id)
        .where(users.c.email == payload["email"])
    )
    record = result.fetchone()

    if not record:
        raise HTTPException(status_code=401, detail="User does not exist")
    if not record.email_verified:
        raise HTTPException(status_code=403, detail="Email not verified")
    
    return record.id