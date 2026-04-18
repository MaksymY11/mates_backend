from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete, update
from app.database import get_db
from app.models import users, device_tokens
from app.deps import require_verified_user
from datetime import datetime, timezone

router = APIRouter(tags=["devices"])

# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id

# ── Device CRUD ──────────────────────────────────────────────────

@router.post("/devices/register")
async def register_device(
    body: dict,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Register or reassign an FCM device token for the current user.
       If the token already exists (e.g. failed logout), reassigns it to the current user.
       Called on app launch after Firebase initialization."""

    me = await _resolve_user_id(db,payload)

    platform = body.get("platform", "")

    fcm_token = body.get("fcm_token", "")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    result = await db.execute(
        select(device_tokens.c.fcm_token).where(device_tokens.c.fcm_token == fcm_token)
    )
    exists = result.fetchone()
    if exists:
        # User Logs in from same device to another account
        await db.execute(
            update(device_tokens)
            .where(device_tokens.c.fcm_token == fcm_token)
            .values(user_id=me)
        )
    else:
        result = await db.execute(
            insert(device_tokens).values(
                user_id = me,
                fcm_token = fcm_token,
                platform = platform,
                created_at = now
            )
        )

    await db.commit()
    return {"detail": "ok"}

@router.delete("/devices/unregister")
async def unregister_device(
    body: dict,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove an FCM device token. Called on logout to stop push notifications for this device."""
    me = await _resolve_user_id(db,payload)
    fcm_token = body["fcm_token"]

    result = await db.execute(
        delete(device_tokens)
        .where(device_tokens.c.fcm_token == fcm_token)
        .where(device_tokens.c.user_id == me)
    )

    await db.commit()
    return {"detail": "ok"}
