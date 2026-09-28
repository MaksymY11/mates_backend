from fastapi import Depends, APIRouter
from app.deps import require_verified_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from app.database import get_db
from pydantic import BaseModel
from app.models import device_tokens, users
from app.security import now
from typing import Literal

router = APIRouter(prefix="/devices", tags=["devices"])

class DeviceRegister(BaseModel):
    fcm_token: str
    platform: Literal["android","ios","web"]

class DeviceUnregister(BaseModel):
    fcm_token: str
    
@router.post("/register")
async def register_device(
    body: DeviceRegister,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """
    - body: DeviceRegister is read from frontend. Contains fcm_token & platform.
    - payload: recieved from require_verified user. Contains user's email and expiration date.
    - db: establishes a new session to connect to the database and to read/write.
    - Creates a new entry in db with user's fcm_token. If fcm_token already exists, moves it to the current user. 
    - One user can have multiple entries if they logged in with different platforms.
    """
    result = await db.execute(
        select(users.c.id)
        .where(users.c.email == payload["email"])
    )
    record = result.fetchone()

    # Always try to delete the token, even without checking if it exists. If it doesn't exist it just returns nothing.
    await db.execute(
        delete(device_tokens)
        .where(device_tokens.c.fcm_token == body.fcm_token)
    )

    await db.execute(
        insert(device_tokens)
        .values(
            user_id = record.id,
            fcm_token = body.fcm_token,
            platform = body.platform,
            created_at = now(),
        )
    )
    await db.commit()

    return {"detail": "fcm_token has been registered."}

@router.delete("/unregister")
async def unregister_device(
    body: DeviceUnregister,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    - body: DeviceUnregister is read from frontend. Contains ONLY fcm_token.
    - payload: recieved from require_verified user. Contains user's email and expiration date.
    - db: establishes a new session to connect to the database and to read/write.
    - Unregisters user's token.
    """
    result = await db.execute(
        select(users.c.id)
        .where(users.c.email == payload["email"])
    )
    record = result.fetchone()

    await db.execute(
        delete(device_tokens)
        .where(device_tokens.c.fcm_token == body.fcm_token, device_tokens.c.user_id == record.id)
    )
    await db.commit()

    return {"detail": "device token has been unregistered."}
    