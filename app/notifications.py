from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select, delete
from app.models import notifications, device_tokens
from app.firebase import send_push
from datetime import datetime, timezone
import asyncio


async def create_notification(
    db: AsyncSession,
    user_id: int,
    event_type: str,
    actor_id: int | None,
    title: str,
    body: str,
    data: dict | None = None,
):
    """Insert a notification row, push via WebSocket to online users,
    and send FCM push notifications to all registered devices.
    Stale FCM tokens are automatically cleaned up on send failure."""

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

    # Push via FCM
    try:
        tokens_result = await db.execute(
            select(device_tokens.c.fcm_token)
            .where(device_tokens.c.user_id == user_id)
        )

        fcm_data = {
            "event_type": event_type,
            "notification_id": str(row.id),
        }
        if data:
            fcm_data.update({k: str(v) for k, v in data.items()})

        stale = []
        for token in tokens_result:
            success = await asyncio.to_thread(send_push, token.fcm_token, title, body, fcm_data)
            if success is False:
                stale.append(token.fcm_token)

        for token in stale:
            await db.execute(
                delete(device_tokens)
                .where(device_tokens.c.fcm_token == token)
            )
    except Exception as e:
        print(f"[NOTIF] FCM push failed for user {user_id}: {e}")