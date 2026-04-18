from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from app.database import get_db
from app.models import notifications, users
from app.deps import require_verified_user

router = APIRouter(prefix="/notifications", tags=["notifications"])

# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id

# ── Notifications CRUD ─────────────────────────────────────────────

@router.get("/")
async def list_notifications(
    limit: int = 50,
    offset: int = 0,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's notifications, newest first, with actor info."""
    me = await _resolve_user_id(db, payload)

    # Total unread count (across all, not just this page)
    result = await db.execute(
        select(func.count()).select_from(notifications).where(
            notifications.c.user_id == me,
            notifications.c.read == False,
        )
    )
    unread_count = result.scalar() or 0

    # Fetch page of notifications joined with actor info
    actor = users.alias("actor")
    query = (
        select(
            notifications,
            actor.c.name.label("actor_name"),
            actor.c.avatar_url.label("actor_avatar_url"),
        )
        .outerjoin(actor, actor.c.id == notifications.c.actor_id)
        .where(notifications.c.user_id == me)
        .order_by(notifications.c.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    rows = result.fetchall()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "event_type": r.event_type,
            "actor_id": r.actor_id,
            "actor_name": r.actor_name,
            "actor_avatar_url": r.actor_avatar_url,
            "title": r.title,
            "body": r.body,
            "data": r.data,
            "read": r.read,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {"notifications": items, "unread_count": unread_count}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    me = await _resolve_user_id(db, payload)
    result = await db.execute(
        update(notifications)
        .where(notifications.c.id == notification_id, notifications.c.user_id == me)
        .values(read=True)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.commit()
    return {"detail": "ok"}


@router.post("/read-all")
async def mark_all_read(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of current user's unread notifications as read."""
    me = await _resolve_user_id(db, payload)
    await db.execute(
        update(notifications)
        .where(notifications.c.user_id == me, notifications.c.read == False)
        .values(read=True)
    )
    await db.commit()
    return {"detail": "ok"}


@router.delete("/")
async def clear_all_notifications(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all notifications for current user."""
    me = await _resolve_user_id(db, payload)
    await db.execute(
        delete(notifications).where(notifications.c.user_id == me)
    )
    await db.commit()
    return {"detail": "ok"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a notification."""
    me = await _resolve_user_id(db, payload)
    result = await db.execute(
        delete(notifications)
        .where(notifications.c.id == notification_id, notifications.c.user_id == me)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.commit()
    return {"detail": "ok"}
