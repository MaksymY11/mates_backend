from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from app.models import notifications, device_tokens
from app.security import now
from app.firebase import send_push
from asyncio import to_thread
import logging

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    recipient_id: int,
    event_type: str,
    actor_id: int | None,
    title: str,
    body: str,
    data: dict | None,
):
    """
    - Inserts a new entry into the notifications table (using the information provided by the caller). Raised on failure.
    - Sends a notification to the recipient via websocket (messaging.py). Logged on failure.
    - Sends a push notification to the recipient via Firebase (firebase.py). Logged on failure.
    - Doesn't commit any changes, caller starts and commits the transaction.
    """
    result = await db.execute(
        insert(notifications)
        .values(
            user_id=recipient_id,
            event_type=event_type,
            actor_id=actor_id,
            title=title,
            body=body,
            data=data,
            created_at=now(),
        ).returning(notifications.c.id, notifications.c.created_at)
    )
    notification = result.fetchone()

    try:
        # imported here to avoid circular import due to messaging.py importing create_notification().
        from app.routes.messaging import manager
        payload = {
            "type": "notification",
            "notification": {
                "id": notification.id,
                "event_type": event_type,
                "actor_id": actor_id,
                "title": title,
                "body": body,
                "data": data,
                "created_at": notification.created_at.isoformat(),
            }
        }
        await manager.send_to_user(recipient_id, payload)
    except Exception:
        logger.exception("Websocket push failed for user %s", recipient_id)
        
    try:
        result = await db.execute(
            select(device_tokens.c.fcm_token)
            .where(device_tokens.c.user_id == recipient_id)
        )
        fcm_tokens = [row.fcm_token for row in result.fetchall()]

        fcm_data = data.copy() if data else {}
        fcm_data["event_type"] = event_type

        for token in fcm_tokens:
            success = await to_thread(send_push, token, title, body, fcm_data)
            if success is False:
                # If token is stale we need to delete it.
                await db.execute(
                    delete(device_tokens)
                    .where(device_tokens.c.fcm_token == token)
                )
    except Exception:
        logger.exception("FCM push failed for user %s", recipient_id)