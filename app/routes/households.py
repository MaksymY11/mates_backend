from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete, update, func, or_, and_
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import (
    users,
    households,
    household_members,
    household_invites,
    house_rules,
    house_rule_votes,
    quick_pick_sessions,
    preference_profiles,
    conversations,
    conversation_participants,
)
from app.deps import get_current_user
from app.notifications import create_notification
from datetime import datetime, timezone, timedelta

router = APIRouter(tags=["households"])


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id


async def _get_user_household(db: AsyncSession, user_id: int):
    """Return the household membership row for a user, or None."""
    result = await db.execute(
        select(household_members).where(household_members.c.user_id == user_id)
    )
    return result.fetchone()


async def _member_count(db: AsyncSession, household_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(household_members)
        .where(household_members.c.household_id == household_id)
    )
    return result.scalar() or 0


async def _has_completed_session(db: AsyncSession, user_a: int, user_b: int) -> bool:
    """Check if two users have a completed Quick Picks session."""
    a, b = min(user_a, user_b), max(user_a, user_b)
    result = await db.execute(
        select(quick_pick_sessions.c.id).where(
            quick_pick_sessions.c.user_a_id == a,
            quick_pick_sessions.c.user_b_id == b,
            quick_pick_sessions.c.status == "completed",
        )
    )
    return result.fetchone() is not None


async def _user_info(db: AsyncSession, user_id: int) -> dict:
    """Compact user info for household member listings."""
    result = await db.execute(
        select(users.c.id, users.c.name, users.c.avatar_url, users.c.city, users.c.state)
        .where(users.c.id == user_id)
    )
    u = result.fetchone()
    if not u:
        return {}

    result = await db.execute(
        select(preference_profiles.c.vibe_labels)
        .where(preference_profiles.c.user_id == user_id)
    )
    prof = result.fetchone()
    vibe_labels = (prof.vibe_labels if prof else None) or []

    return {
        "id": u.id,
        "name": u.name,
        "avatar_url": u.avatar_url,
        "city": u.city,
        "state": u.state,
        "vibe_labels": vibe_labels,
    }


async def _resolve_rule(db: AsyncSession, household_id: int, member_count: int, rule_id: int) -> str | None:
    """After a vote, check if a rule should be auto-resolved. Returns new status or None."""
    # Get current rule status to determine resolution semantics
    result = await db.execute(
        select(house_rules.c.status, house_rules.c.text).where(house_rules.c.id == rule_id)
    )
    rule_row = result.fetchone()
    current_status = rule_row.status
    rule_text = rule_row.text

    result = await db.execute(
        select(
            func.count().filter(house_rule_votes.c.vote == True).label("yes"),
            func.count().filter(house_rule_votes.c.vote == False).label("no"),
        ).where(house_rule_votes.c.rule_id == rule_id)
    )
    row = result.fetchone()
    yes_count = row.yes or 0
    no_count = row.no or 0

    if member_count <= 2:
        threshold = member_count
    else:
        threshold = (member_count // 2) + 1

    new_status = None
    if current_status == "removal_proposed":
        # Yes = remove the rule, No = keep it
        if yes_count >= threshold:
            new_status = "rejected"
        elif no_count >= threshold:
            new_status = "accepted"
    else:
        if yes_count >= threshold:
            new_status = "accepted"
        elif no_count >= threshold:
            new_status = "rejected"

    if new_status:
        await db.execute(
            update(house_rules)
            .where(house_rules.c.id == rule_id)
            .values(status=new_status)
        )

        # Notify all household members: rule_resolved
        result = await db.execute(
            select(household_members.c.user_id)
            .where(household_members.c.household_id == household_id)
        )
        member_ids = [r.user_id for r in result.fetchall()]
        for uid in member_ids:
            await create_notification(
                db, uid, "rule_resolved", None,
                f"Rule {new_status}: {rule_text}",
                "House rule vote completed",
                {"household_id": household_id, "rule_id": rule_id},
            )

    return new_status


# ── Household CRUD ───────────────────────────────────────────────

@router.post("/households/")
async def create_household(
    body: dict,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a household. Creator auto-becomes a member with role 'creator'."""
    me = await _resolve_user_id(db, payload)

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Household name is required")

    existing = await _get_user_household(db, me)
    if existing:
        raise HTTPException(status_code=409, detail="Already in a household")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        insert(households).values(
            name=name,
            created_by=me,
            created_at=now,
            updated_at=now,
        ).returning(households.c.id)
    )
    household_id = result.scalar_one()

    await db.execute(
        insert(household_members).values(
            household_id=household_id,
            user_id=me,
            role="creator",
            joined_at=now,
        )
    )

    # Auto-create group conversation for the household
    conv_result = await db.execute(
        insert(conversations).values(
            type="group",
            household_id=household_id,
            created_at=now,
        ).returning(conversations.c.id)
    )
    conv_id = conv_result.scalar_one()
    await db.execute(
        insert(conversation_participants).values(
            conversation_id=conv_id,
            user_id=me,
            joined_at=now,
            last_read_at=None,
        )
    )

    await db.commit()
    return {"id": household_id, "name": name}


@router.get("/households/me")
async def get_my_household(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's household with members and rules."""
    me = await _resolve_user_id(db, payload)
    membership = await _get_user_household(db, me)

    if not membership:
        return {"household": None}

    hid = membership.household_id

    result = await db.execute(
        select(households).where(households.c.id == hid)
    )
    h = result.fetchone()
    if not h:
        return {"household": None}

    # Fetch members with user info
    result = await db.execute(
        select(household_members)
        .where(household_members.c.household_id == hid)
        .order_by(household_members.c.joined_at)
    )
    members_rows = result.fetchall()
    members = []
    for m in members_rows:
        info = await _user_info(db, m.user_id)
        info["role"] = m.role
        info["joined_at"] = m.joined_at.isoformat() if m.joined_at else None
        members.append(info)

    # Fetch rules with vote info
    result = await db.execute(
        select(house_rules)
        .where(house_rules.c.household_id == hid)
        .order_by(house_rules.c.created_at)
    )
    rules_rows = result.fetchall()
    rules = []
    for r in rules_rows:
        result = await db.execute(
            select(
                func.count().filter(house_rule_votes.c.vote == True).label("yes"),
                func.count().filter(house_rule_votes.c.vote == False).label("no"),
            ).where(house_rule_votes.c.rule_id == r.id)
        )
        votes = result.fetchone()

        result = await db.execute(
            select(house_rule_votes.c.vote).where(
                house_rule_votes.c.rule_id == r.id,
                house_rule_votes.c.user_id == me,
            )
        )
        my_vote_row = result.fetchone()

        rules.append({
            "id": r.id,
            "text": r.text,
            "proposed_by": r.proposed_by,
            "status": r.status,
            "yes_votes": votes.yes or 0,
            "no_votes": votes.no or 0,
            "my_vote": my_vote_row.vote if my_vote_row else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    # Get group conversation ID for this household
    result = await db.execute(
        select(conversations.c.id).where(
            conversations.c.household_id == hid,
            conversations.c.type == "group",
        )
    )
    conv_row = result.fetchone()
    conversation_id = conv_row.id if conv_row else None

    return {
        "household": {
            "id": h.id,
            "name": h.name,
            "created_by": h.created_by,
            "conversation_id": conversation_id,
            "members": members,
            "rules": rules,
        }
    }


@router.post("/households/leave")
async def leave_household(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Leave current household. Transfers creator role if needed. Deletes if last member."""
    me = await _resolve_user_id(db, payload)
    membership = await _get_user_household(db, me)
    if not membership:
        raise HTTPException(status_code=404, detail="Not in a household")

    hid = membership.household_id
    count = await _member_count(db, hid)

    await db.execute(
        delete(household_members).where(household_members.c.user_id == me)
    )

    if count <= 1:
        await db.execute(delete(households).where(households.c.id == hid))
    elif membership.role == "creator":
        result = await db.execute(
            select(household_members)
            .where(household_members.c.household_id == hid)
            .order_by(household_members.c.joined_at)
            .limit(1)
        )
        next_creator = result.fetchone()
        if next_creator:
            await db.execute(
                update(household_members)
                .where(household_members.c.id == next_creator.id)
                .values(role="creator")
            )

    await db.execute(
        delete(household_invites).where(
            household_invites.c.household_id == hid,
            household_invites.c.inviter_id == me,
            household_invites.c.status == "pending",
        )
    )

    # Remove from group conversation
    result = await db.execute(
        select(conversations.c.id).where(
            conversations.c.household_id == hid,
            conversations.c.type == "group",
        )
    )
    conv_row = result.fetchone()
    if conv_row:
        await db.execute(
            delete(conversation_participants).where(
                conversation_participants.c.conversation_id == conv_row.id,
                conversation_participants.c.user_id == me,
            )
        )

    await db.commit()
    return {"detail": "Left household"}


@router.delete("/households/{household_id}")
async def delete_household(
    household_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete household (creator only). Cascade deletes members, rules, votes, invites."""
    me = await _resolve_user_id(db, payload)
    membership = await _get_user_household(db, me)

    if not membership or membership.household_id != household_id:
        raise HTTPException(status_code=404, detail="Not in this household")
    if membership.role != "creator":
        raise HTTPException(status_code=403, detail="Only the creator can delete the household")

    await db.execute(
        delete(household_members).where(household_members.c.household_id == household_id)
    )
    await db.execute(delete(households).where(households.c.id == household_id))

    await db.commit()
    return {"detail": "Household deleted"}


# ── Invites ──────────────────────────────────────────────────────

@router.post("/households/invite/{user_id}")
async def invite_user(
    user_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user to current household. Requires completed Quick Picks session."""
    me = await _resolve_user_id(db, payload)
    membership = await _get_user_household(db, me)

    if not membership:
        raise HTTPException(status_code=400, detail="You must be in a household to invite")
    if me == user_id:
        raise HTTPException(status_code=400, detail="Cannot invite yourself")

    hid = membership.household_id

    count = await _member_count(db, hid)
    if count >= 4:
        raise HTTPException(status_code=400, detail="Household is full (max 4 members)")

    result = await db.execute(select(users.c.id).where(users.c.id == user_id))
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    invitee_membership = await _get_user_household(db, user_id)
    if invitee_membership:
        raise HTTPException(status_code=409, detail="User is already in a household")

    has_session = await _has_completed_session(db, me, user_id)
    if not has_session:
        raise HTTPException(status_code=400, detail="Must have a completed Quick Picks session to invite")

    result = await db.execute(
        select(household_invites.c.id).where(
            household_invites.c.household_id == hid,
            household_invites.c.invitee_id == user_id,
            household_invites.c.status == "pending",
        )
    )
    if result.fetchone():
        raise HTTPException(status_code=409, detail="Pending invite already exists")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        await db.execute(
            insert(household_invites).values(
                household_id=hid,
                inviter_id=me,
                invitee_id=user_id,
                status="pending",
                created_at=now,
            )
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Invite already exists")

    # Get household name and actor name for notification
    result = await db.execute(select(households.c.name).where(households.c.id == hid))
    h_name = result.scalar()
    result = await db.execute(select(users.c.name).where(users.c.id == me))
    my_name = result.scalar()

    await create_notification(
        db, user_id, "household_invite", me,
        f"{my_name} invited you to join {h_name}",
        "Tap to view the invite",
        {"household_id": hid},
    )

    await db.commit()
    return {"detail": "Invite sent"}


@router.get("/households/invites")
async def list_invites(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List pending invites — both sent and received."""
    me = await _resolve_user_id(db, payload)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=7)

    # Clean up expired pending invites involving this user
    await db.execute(
        delete(household_invites).where(
            household_invites.c.status == "pending",
            household_invites.c.created_at < cutoff,
            or_(
                household_invites.c.invitee_id == me,
                household_invites.c.inviter_id == me,
            ),
        )
    )
    await db.commit()

    # Received invites (only non-expired pending)
    result = await db.execute(
        select(household_invites, households.c.name.label("household_name"))
        .join(households, households.c.id == household_invites.c.household_id)
        .where(
            household_invites.c.invitee_id == me,
            household_invites.c.status == "pending",
        )
    )
    received = []
    for row in result.fetchall():
        inviter_info = await _user_info(db, row.inviter_id)
        received.append({
            "id": row.id,
            "household_id": row.household_id,
            "household_name": row.household_name,
            "inviter": inviter_info,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    # Sent invites
    result = await db.execute(
        select(household_invites)
        .where(
            household_invites.c.inviter_id == me,
            household_invites.c.status == "pending",
        )
    )
    sent = []
    for row in result.fetchall():
        invitee_info = await _user_info(db, row.invitee_id)
        sent.append({
            "id": row.id,
            "household_id": row.household_id,
            "invitee": invitee_info,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })

    return {"received": received, "sent": sent}


@router.post("/households/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept an invite and join the household as 'member'."""
    me = await _resolve_user_id(db, payload)

    result = await db.execute(
        select(household_invites).where(household_invites.c.id == invite_id)
    )
    invite = result.fetchone()
    if not invite or invite.invitee_id != me:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invite is no longer pending")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Check expiration (7 days)
    if invite.created_at and (now - invite.created_at) > timedelta(days=7):
        await db.execute(delete(household_invites).where(household_invites.c.id == invite_id))
        await db.commit()
        raise HTTPException(status_code=410, detail="Invite has expired")

    existing = await _get_user_household(db, me)
    if existing:
        raise HTTPException(status_code=409, detail="Already in a household")

    count = await _member_count(db, invite.household_id)
    if count >= 4:
        # Household filled up — delete this stale invite
        await db.execute(delete(household_invites).where(household_invites.c.id == invite_id))
        await db.commit()
        raise HTTPException(status_code=400, detail="Household is full")

    try:
        await db.execute(
            insert(household_members).values(
                household_id=invite.household_id,
                user_id=me,
                role="member",
                joined_at=now,
            )
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Already in a household")

    # Add to group conversation
    result = await db.execute(
        select(conversations.c.id).where(
            conversations.c.household_id == invite.household_id,
            conversations.c.type == "group",
        )
    )
    conv_row = result.fetchone()
    if conv_row:
        await db.execute(
            insert(conversation_participants).values(
                conversation_id=conv_row.id,
                user_id=me,
                joined_at=now,
                last_read_at=None,
            )
        )

    # Delete this invite and all other pending invites for this user
    await db.execute(
        delete(household_invites).where(
            household_invites.c.invitee_id == me,
            household_invites.c.status == "pending",
        )
    )

    # Notify existing members (not the joiner)
    result = await db.execute(select(users.c.name).where(users.c.id == me))
    joiner_name = result.scalar()
    result = await db.execute(
        select(household_members.c.user_id)
        .where(household_members.c.household_id == invite.household_id)
    )
    for row in result.fetchall():
        if row.user_id != me:
            await create_notification(
                db, row.user_id, "household_member_joined", me,
                f"{joiner_name} joined your household!",
                "Your household is growing",
                {"household_id": invite.household_id},
            )

    await db.commit()
    return {"detail": "Joined household"}


@router.post("/households/invites/{invite_id}/decline")
async def decline_invite(
    invite_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decline a household invite."""
    me = await _resolve_user_id(db, payload)

    result = await db.execute(
        select(household_invites).where(household_invites.c.id == invite_id)
    )
    invite = result.fetchone()
    if not invite or invite.invitee_id != me:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Invite is no longer pending")

    await db.execute(
        delete(household_invites).where(household_invites.c.id == invite_id)
    )
    await db.commit()
    return {"detail": "Invite declined"}


# ── House Rules ──────────────────────────────────────────────────

@router.get("/households/{household_id}/rules")
async def list_rules(
    household_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all rules with vote counts and current user's vote."""
    me = await _resolve_user_id(db, payload)
    membership = await _get_user_household(db, me)
    if not membership or membership.household_id != household_id:
        raise HTTPException(status_code=403, detail="Not a member of this household")

    result = await db.execute(
        select(house_rules)
        .where(house_rules.c.household_id == household_id)
        .order_by(house_rules.c.created_at)
    )
    rules_rows = result.fetchall()
    rules = []
    for r in rules_rows:
        result = await db.execute(
            select(
                func.count().filter(house_rule_votes.c.vote == True).label("yes"),
                func.count().filter(house_rule_votes.c.vote == False).label("no"),
            ).where(house_rule_votes.c.rule_id == r.id)
        )
        votes = result.fetchone()

        result = await db.execute(
            select(house_rule_votes.c.vote).where(
                house_rule_votes.c.rule_id == r.id,
                house_rule_votes.c.user_id == me,
            )
        )
        my_vote_row = result.fetchone()

        result = await db.execute(
            select(users.c.name).where(users.c.id == r.proposed_by)
        )
        proposer = result.fetchone()

        rules.append({
            "id": r.id,
            "text": r.text,
            "proposed_by": r.proposed_by,
            "proposed_by_name": proposer.name if proposer else None,
            "status": r.status,
            "yes_votes": votes.yes or 0,
            "no_votes": votes.no or 0,
            "my_vote": my_vote_row.vote if my_vote_row else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {"rules": rules}


@router.post("/households/{household_id}/rules")
async def propose_rule(
    household_id: int,
    body: dict,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Propose a new house rule."""
    me = await _resolve_user_id(db, payload)
    membership = await _get_user_household(db, me)
    if not membership or membership.household_id != household_id:
        raise HTTPException(status_code=403, detail="Not a member of this household")

    count = await _member_count(db, household_id)
    if count < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 members to propose rules")

    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Rule text is required")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        insert(house_rules).values(
            household_id=household_id,
            text=text,
            proposed_by=me,
            status="proposed",
            created_at=now,
        ).returning(house_rules.c.id)
    )
    rule_id = result.scalar_one()

    # Auto-vote yes from the proposer
    await db.execute(
        insert(house_rule_votes).values(
            rule_id=rule_id,
            user_id=me,
            vote=True,
        )
    )

    # Notify other members: rule_proposed
    result = await db.execute(select(users.c.name).where(users.c.id == me))
    my_name = result.scalar()
    result = await db.execute(
        select(household_members.c.user_id)
        .where(household_members.c.household_id == household_id)
    )
    for row in result.fetchall():
        if row.user_id != me:
            await create_notification(
                db, row.user_id, "rule_proposed", me,
                f"{my_name} proposed: {text}",
                "Vote on this house rule",
                {"household_id": household_id, "rule_id": rule_id},
            )

    # Check if proposer's vote triggers majority (e.g. 2 of 3 members)
    count = await _member_count(db, household_id)
    await _resolve_rule(db, household_id, count, rule_id)

    await db.commit()

    result = await db.execute(
        select(house_rules.c.status).where(house_rules.c.id == rule_id)
    )
    final_status = result.scalar() or "proposed"

    return {"id": rule_id, "text": text, "status": final_status}


@router.post("/households/rules/{rule_id}/vote")
async def vote_on_rule(
    rule_id: int,
    body: dict,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vote on a house rule. Auto-resolves when majority reached."""
    me = await _resolve_user_id(db, payload)

    vote_val = body.get("vote")
    if vote_val is None:
        raise HTTPException(status_code=400, detail="vote field is required (true/false)")

    result = await db.execute(
        select(house_rules).where(house_rules.c.id == rule_id)
    )
    rule = result.fetchone()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    membership = await _get_user_household(db, me)
    if not membership or membership.household_id != rule.household_id:
        raise HTTPException(status_code=403, detail="Not a member of this household")

    if rule.status not in ("proposed", "removal_proposed"):
        raise HTTPException(status_code=400, detail="Can only vote on proposed or removal-proposed rules")

    # Upsert vote
    result = await db.execute(
        select(house_rule_votes.c.id).where(
            house_rule_votes.c.rule_id == rule_id,
            house_rule_votes.c.user_id == me,
        )
    )
    existing_vote = result.fetchone()
    if existing_vote:
        await db.execute(
            update(house_rule_votes)
            .where(house_rule_votes.c.id == existing_vote.id)
            .values(vote=vote_val)
        )
    else:
        await db.execute(
            insert(house_rule_votes).values(
                rule_id=rule_id,
                user_id=me,
                vote=vote_val,
            )
        )

    count = await _member_count(db, rule.household_id)
    await _resolve_rule(db, rule.household_id, count, rule_id)

    await db.commit()

    result = await db.execute(
        select(house_rules.c.status).where(house_rules.c.id == rule_id)
    )
    new_status = result.scalar()

    return {"detail": "Vote recorded", "rule_status": new_status}


@router.post("/households/rules/{rule_id}/propose-removal")
async def propose_rule_removal(
    rule_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Propose removal of an accepted rule. Resets votes, starts a removal vote."""
    me = await _resolve_user_id(db, payload)

    result = await db.execute(
        select(house_rules).where(house_rules.c.id == rule_id)
    )
    rule = result.fetchone()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.status != "accepted":
        raise HTTPException(status_code=400, detail="Can only propose removal of accepted rules")

    membership = await _get_user_household(db, me)
    if not membership or membership.household_id != rule.household_id:
        raise HTTPException(status_code=403, detail="Not a member of this household")

    # Clear existing votes and set status to removal_proposed
    await db.execute(
        delete(house_rule_votes).where(house_rule_votes.c.rule_id == rule_id)
    )
    await db.execute(
        update(house_rules)
        .where(house_rules.c.id == rule_id)
        .values(status="removal_proposed")
    )

    # Auto-vote yes (proposer wants removal)
    await db.execute(
        insert(house_rule_votes).values(
            rule_id=rule_id,
            user_id=me,
            vote=True,
        )
    )

    # Notify other members: removal_proposed
    result = await db.execute(select(users.c.name).where(users.c.id == me))
    my_name = result.scalar()
    result = await db.execute(
        select(household_members.c.user_id)
        .where(household_members.c.household_id == rule.household_id)
    )
    for row in result.fetchall():
        if row.user_id != me:
            await create_notification(
                db, row.user_id, "removal_proposed", me,
                f"{my_name} proposes removing: {rule.text}",
                "Vote on whether to keep this rule",
                {"household_id": rule.household_id, "rule_id": rule_id},
            )

    # Auto-resolve in case proposer's vote is enough
    count = await _member_count(db, rule.household_id)
    await _resolve_rule(db, rule.household_id, count, rule_id)

    await db.commit()

    result = await db.execute(
        select(house_rules.c.status).where(house_rules.c.id == rule_id)
    )
    final_status = result.scalar()

    return {"detail": "Removal proposed", "rule_status": final_status}


@router.delete("/households/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a rule (proposer or creator only)."""
    me = await _resolve_user_id(db, payload)

    membership = await _get_user_household(db, me)
    if not membership:
        raise HTTPException(status_code=404, detail="Rule not found")

    result = await db.execute(
        select(house_rules)
        .where(house_rules.c.id == rule_id, house_rules.c.household_id == membership.household_id,)
    )
    rule = result.fetchone()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if rule.proposed_by != me and membership.role != "creator":
        raise HTTPException(status_code=403, detail="Only the proposer or household creator can delete rules")

    await db.execute(
        delete(house_rule_votes).where(house_rule_votes.c.rule_id == rule_id)
    )
    await db.execute(
        delete(house_rules).where(house_rules.c.id == rule_id)
    )

    await db.commit()
    return {"detail": "Rule deleted"}


# ── Eligible Connections ─────────────────────────────────────────

@router.get("/households/eligible")
async def list_eligible_connections(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List users with completed Quick Picks sessions who aren't in a household."""
    me = await _resolve_user_id(db, payload)

    result = await db.execute(
        select(quick_pick_sessions).where(
            quick_pick_sessions.c.status == "completed",
            or_(
                quick_pick_sessions.c.user_a_id == me,
                quick_pick_sessions.c.user_b_id == me,
            ),
        )
    )
    sessions = result.fetchall()

    eligible = []
    seen = set()
    for s in sessions:
        other_id = s.user_b_id if s.user_a_id == me else s.user_a_id
        if other_id in seen:
            continue
        seen.add(other_id)

        other_membership = await _get_user_household(db, other_id)
        if other_membership:
            continue

        info = await _user_info(db, other_id)
        if info:
            eligible.append(info)

    return {"eligible": eligible}
