from fastapi import Depends, APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, func
from app.database import get_db, AsyncSessionLocal
from app.models import (
    users,
    conversations,
    conversation_participants,
    messages,
    quick_pick_sessions,
    notifications,
)
from app.deps import require_verified_user
from app.auth import verify_access_token
from app.notifications import create_notification
from datetime import datetime, timezone
import json
import asyncio

router = APIRouter(tags=["messaging"])


# ── Connection Manager ──────────────────────────────────────────
# In-memory singleton — works for a single server instance.
# TODO: Replace with Redis pub/sub for multi-instance scaling.

class ConnectionManager:
    def __init__(self):
        self.active: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        # Replace previous connection for same user
        old = self.active.get(user_id)
        if old:
            try:
                await old.close()
            except Exception:
                pass
        self.active[user_id] = ws

    def disconnect(self, user_id: int):
        self.active.pop(user_id, None)

    async def send_to_user(self, user_id: int, data: dict):
        ws = self.active.get(user_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.disconnect(user_id)


manager = ConnectionManager()


# ── Helpers ─────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    record = result.fetchone()
    if not record:
        raise HTTPException(status_code=404, detail="User not found")
    return record.id


async def _has_completed_session(db: AsyncSession, user_a: int, user_b: int) -> bool:
    a, b = min(user_a, user_b), max(user_a, user_b)
    result = await db.execute(
        select(quick_pick_sessions.c.id).where(
            quick_pick_sessions.c.user_a_id == a,
            quick_pick_sessions.c.user_b_id == b,
            quick_pick_sessions.c.status == "completed",
        )
    )
    return result.fetchone() is not None


async def _get_participant_ids(db: AsyncSession, conversation_id: int) -> list[int]:
    result = await db.execute(
        select(conversation_participants.c.user_id)
        .where(conversation_participants.c.conversation_id == conversation_id)
    )
    return [row.user_id for row in result.fetchall()]


# ── WebSocket Endpoint ──────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    # Wait for auth frame (5 sec timeout)
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout = 5.0)
        data = json.loads(raw)
        if data.get("type") != "auth" or not data.get("token"):
            await ws.close(code=4001)
            return
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        await ws.close(code=4001)
        return
    
    payload = verify_access_token(data["token"])
    if not payload:
        await ws.close(code=4001)
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(users.c.id, users.c.email_verified).where(users.c.email == payload["email"])
        )
        record = result.fetchone()
        if not record:
            await ws.close(code=4001)
            return
        user_id = record.id
        if not record.email_verified:
            await ws.close(code=4003)
            return

    await manager.connect(user_id, ws)

    try:
        bad_msg_counter = 0
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                bad_msg_counter += 1
                if bad_msg_counter > 10:
                    await ws.close()
                    manager.disconnect(user_id)
                    break
                continue

            msg_type = data.get("type")

            bad_msg_counter = 0
            if msg_type == "message":
                await _handle_ws_message(user_id, data)
            elif msg_type == "typing":
                await _handle_ws_typing(user_id, data)
            elif msg_type == "read":
                await _handle_ws_read(user_id, data)

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception:
        manager.disconnect(user_id)


async def _handle_ws_message(sender_id: int, data: dict):
    conv_id = data.get("conversation_id")
    body = data.get("body", "").strip()
    if not conv_id or not body:
        return

    async with AsyncSessionLocal() as db:
        # Validate sender is a participant
        participant_ids = await _get_participant_ids(db, conv_id)
        if sender_id not in participant_ids:
            return

        # Persist message
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await db.execute(
            insert(messages).values(
                conversation_id=conv_id,
                sender_id=sender_id,
                body=body,
                created_at=now,
            ).returning(messages.c.id, messages.c.created_at)
        )
        msg_row = result.fetchone()
        await db.commit()

        # Get sender name for fan-out
        result = await db.execute(
            select(users.c.name, users.c.avatar_url).where(users.c.id == sender_id)
        )
        sender = result.fetchone()

    # Fan out to all participants
    sender_name = sender.name if sender else None
    outgoing = {
        "type": "message",
        "conversation_id": conv_id,
        "message": {
            "id": msg_row.id,
            "conversation_id": conv_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "sender_avatar_url": sender.avatar_url if sender else None,
            "body": body,
            "created_at": msg_row.created_at.isoformat(),
        },
    }
    for uid in participant_ids:
        if uid != sender_id:
            await manager.send_to_user(uid, outgoing)

    # Notify all non-sender participants — upsert per conversation
    preview = body[:100]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as notify_db:
        result = await notify_db.execute(
            select(conversations.c.type, conversations.c.household_id)
            .where(conversations.c.id == conv_id)
        )
        conv = result.fetchone()

        for uid in participant_ids:
            if uid != sender_id:
                if conv and conv.type == "group":
                    from app.models import households as households_table
                    result = await notify_db.execute(
                        select(households_table.c.name)
                        .where(households_table.c.id == conv.household_id)
                    )
                    h_name = result.scalar()
                    event_type = "new_group_message"
                    title = f"{sender_name} in {h_name}: {preview}"
                else:
                    event_type = "new_dm_message"
                    title = f"New message from {sender_name}"

                # Upsert: find existing message notification for this conversation
                result = await notify_db.execute(
                    select(notifications.c.id).where(
                        notifications.c.user_id == uid,
                        notifications.c.event_type.in_(["new_dm_message", "new_group_message"]),
                        notifications.c.data["conversation_id"].as_integer() == conv_id,
                    )
                )
                existing = result.fetchone()

                if existing:
                    await notify_db.execute(
                        update(notifications)
                        .where(notifications.c.id == existing.id)
                        .values(
                            event_type=event_type,
                            title=title,
                            body=preview,
                            actor_id=sender_id,
                            read=False,
                            created_at=now,
                        )
                    )
                    await notify_db.commit()
                    # Push via WebSocket
                    try:
                        await manager.send_to_user(uid, {
                            "type": "notification",
                            "notification": {
                                "id": existing.id,
                                "event_type": event_type,
                                "actor_id": sender_id,
                                "title": title,
                                "body": preview,
                                "data": {"conversation_id": conv_id, "user_id": sender_id},
                                "created_at": now.isoformat(),
                            },
                        })
                    except Exception:
                        pass
                else:
                    await create_notification(
                        notify_db, uid, event_type, sender_id,
                        title, preview,
                        {"conversation_id": conv_id, "user_id": sender_id},
                    )
                    await notify_db.commit()


async def _handle_ws_typing(sender_id: int, data: dict):
    conv_id = data.get("conversation_id")
    if not conv_id:
        return

    async with AsyncSessionLocal() as db:
        participant_ids = await _get_participant_ids(db, conv_id)
        if sender_id not in participant_ids:
            return

        result = await db.execute(
            select(users.c.name).where(users.c.id == sender_id)
        )
        sender = result.fetchone()

    outgoing = {
        "type": "typing",
        "conversation_id": conv_id,
        "user_id": sender_id,
        "user_name": sender.name if sender else None,
    }
    for uid in participant_ids:
        if uid != sender_id:
            await manager.send_to_user(uid, outgoing)


async def _handle_ws_read(user_id: int, data: dict):
    conv_id = data.get("conversation_id")
    if not conv_id:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(conversation_participants)
            .where(
                conversation_participants.c.conversation_id == conv_id,
                conversation_participants.c.user_id == user_id,
            )
            .values(last_read_at=now)
        )
        await db.commit()


# ── REST Endpoints ──────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's conversations with last message and unread count."""
    me = await _resolve_user_id(db, payload)

    # Get all conversation IDs for this user
    result = await db.execute(
        select(conversation_participants.c.conversation_id, conversation_participants.c.last_read_at)
        .where(conversation_participants.c.user_id == me)
    )
    my_participations = {row.conversation_id: row.last_read_at for row in result.fetchall()}

    if not my_participations:
        return {"conversations": []}

    conv_ids = list(my_participations.keys())

    # Fetch conversation rows
    result = await db.execute(
        select(conversations).where(conversations.c.id.in_(conv_ids))
    )
    conv_rows = {c.id: c for c in result.fetchall()}

    items = []
    for conv_id in conv_ids:
        conv = conv_rows.get(conv_id)
        if not conv:
            continue

        # Last message
        result = await db.execute(
            select(messages)
            .where(messages.c.conversation_id == conv_id)
            .order_by(messages.c.id.desc())
            .limit(1)
        )
        last_msg = result.fetchone()

        # Unread count
        last_read = my_participations[conv_id]
        if last_read:
            result = await db.execute(
                select(func.count()).select_from(messages).where(
                    messages.c.conversation_id == conv_id,
                    messages.c.created_at > last_read,
                    messages.c.sender_id != me,
                )
            )
        else:
            result = await db.execute(
                select(func.count()).select_from(messages).where(
                    messages.c.conversation_id == conv_id,
                    messages.c.sender_id != me,
                )
            )
        unread_count = result.scalar() or 0

        # Participants info
        result = await db.execute(
            select(
                conversation_participants.c.user_id,
                users.c.name,
                users.c.avatar_url,
            )
            .join(users, users.c.id == conversation_participants.c.user_id)
            .where(conversation_participants.c.conversation_id == conv_id)
        )
        participants = [
            {"id": r.user_id, "name": r.name, "avatar_url": r.avatar_url}
            for r in result.fetchall()
        ]

        # Last message sender name
        last_message = None
        if last_msg:
            sender_name = None
            for p in participants:
                if p["id"] == last_msg.sender_id:
                    sender_name = p["name"]
                    break
            last_message = {
                "body": last_msg.body,
                "sender_name": sender_name,
                "created_at": last_msg.created_at.isoformat() if last_msg.created_at else None,
            }

        items.append({
            "id": conv.id,
            "type": conv.type,
            "household_id": conv.household_id,
            "participants": participants,
            "last_message": last_message,
            "unread_count": unread_count,
        })

    # Sort by last message time descending (conversations with messages first)
    items.sort(
        key=lambda c: c["last_message"]["created_at"] if c["last_message"] else "",
        reverse=True,
    )

    return {"conversations": items}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    before: int | None = None,
    limit: int = 50,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Cursor-paginated message history. Ordered by created_at ASC."""
    me = await _resolve_user_id(db, payload)

    # Verify participant
    participant_ids = await _get_participant_ids(db, conversation_id)
    if me not in participant_ids:
        raise HTTPException(status_code=403, detail="Not a participant")

    query = select(messages).where(messages.c.conversation_id == conversation_id)
    if before is not None:
        query = query.where(messages.c.id < before)

    query = query.order_by(messages.c.id.desc()).limit(limit)
    result = await db.execute(query)
    rows = result.fetchall()

    # Reverse to ASC order for display
    rows = list(reversed(rows))

    # Batch-fetch sender info
    sender_ids = list({r.sender_id for r in rows})
    sender_map = {}
    if sender_ids:
        result = await db.execute(
            select(users.c.id, users.c.name, users.c.avatar_url)
            .where(users.c.id.in_(sender_ids))
        )
        for u in result.fetchall():
            sender_map[u.id] = {"name": u.name, "avatar_url": u.avatar_url}

    msgs = []
    for r in rows:
        sender = sender_map.get(r.sender_id, {})
        msgs.append({
            "id": r.id,
            "conversation_id": r.conversation_id,
            "sender_id": r.sender_id,
            "sender_name": sender.get("name"),
            "sender_avatar_url": sender.get("avatar_url"),
            "body": r.body,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {"messages": msgs}


@router.post("/conversations/dm/{user_id}")
async def create_dm(
    user_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or return existing DM conversation. Requires completed Quick Picks."""
    me = await _resolve_user_id(db, payload)

    if me == user_id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    # Verify target exists
    result = await db.execute(select(users.c.id).where(users.c.id == user_id))
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    # Validate completed Quick Picks session
    has_session = await _has_completed_session(db, me, user_id)
    if not has_session:
        raise HTTPException(status_code=400, detail="Must have a completed Quick Picks session to message")

    # Check for existing DM — look for a conversation where both users are participants and type is "dm"
    # Use normalized pair ordering (lower user_id first) for consistent lookup
    a, b = min(me, user_id), max(me, user_id)

    result = await db.execute(
        select(conversation_participants.c.conversation_id)
        .where(conversation_participants.c.user_id == a)
    )
    a_convs = {row.conversation_id for row in result.fetchall()}

    if a_convs:
        result = await db.execute(
            select(conversation_participants.c.conversation_id)
            .where(
                conversation_participants.c.user_id == b,
                conversation_participants.c.conversation_id.in_(a_convs),
            )
        )
        shared_convs = [row.conversation_id for row in result.fetchall()]

        for cid in shared_convs:
            result = await db.execute(
                select(conversations.c.id).where(
                    conversations.c.id == cid,
                    conversations.c.type == "dm",
                )
            )
            if result.fetchone():
                return {"conversation_id": cid, "created": False}

    # Create new DM conversation
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        insert(conversations).values(
            type="dm",
            household_id=None,
            created_at=now,
        ).returning(conversations.c.id)
    )
    conv_id = result.scalar_one()

    # Add both participants (lower ID first for consistency)
    for uid in (a, b):
        await db.execute(
            insert(conversation_participants).values(
                conversation_id=conv_id,
                user_id=uid,
                joined_at=now,
                last_read_at=None,
            )
        )

    await db.commit()
    return {"conversation_id": conv_id, "created": True}


@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark conversation as read for current user."""
    me = await _resolve_user_id(db, payload)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        update(conversation_participants)
        .where(
            conversation_participants.c.conversation_id == conversation_id,
            conversation_participants.c.user_id == me,
        )
        .values(last_read_at=now)
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=403, detail="Not a participant")

    await db.commit()
    return {"detail": "Marked as read"}
