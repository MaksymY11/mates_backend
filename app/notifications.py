from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert
from app.models import notifications
from datetime import datetime, timezone


async def create_notification(
    db: AsyncSession,
    user_id: int,
    event_type: str,
    actor_id: int | None,
    title: str,
    body: str,
    data: dict | None = None,
):
    """Insert a notification row and push it via WebSocket if the user is online."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        insert(notifications).values(
            user_id=user_id,
            event_type=event_type,
            actor_id=actor_id,
            title=title,
            body=body,
            data=data,
            read=False,
            created_at=now,
        ).returning(notifications.c.id, notifications.c.created_at)
    )
    row = result.fetchone()

    # Push via WebSocket (import here to avoid circular imports)
    try:
        from app.routes.messaging import manager
        print(f"[NOTIF] Pushing to user {user_id}, active WS users: {list(manager.active.keys())}")
        await manager.send_to_user(user_id, {
            "type": "notification",
            "notification": {
                "id": row.id,
                "event_type": event_type,
                "actor_id": actor_id,
                "title": title,
                "body": body,
                "data": data,
                "created_at": row.created_at.isoformat(),
            },
        })
        print(f"[NOTIF] Push sent successfully to user {user_id}")
    except Exception as e:
        print(f"[NOTIF] WebSocket push failed for user {user_id}: {e}")
