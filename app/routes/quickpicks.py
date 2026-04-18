from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete, func, or_, and_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.database import get_db
from app.models import (
    users,
    interests,
    quick_pick_questions,
    quick_pick_sessions,
    quick_pick_answers,
    preference_profiles,
)
from app.deps import require_verified_user
from app.notifications import create_notification
from datetime import datetime, timezone
import random

router = APIRouter(tags=["quickpicks"])


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id


async def _create_session(db: AsyncSession, user_a_id: int, user_b_id: int) -> int:
    """Create a Quick Picks session with 5 randomly selected questions.

    Normalizes user pair so user_a_id < user_b_id to enforce the unique constraint
    on unordered pairs.
    """
    # Normalize pair ordering
    a, b = min(user_a_id, user_b_id), max(user_a_id, user_b_id)

    # Check if session already exists
    result = await db.execute(
        select(quick_pick_sessions.c.id).where(
            quick_pick_sessions.c.user_a_id == a,
            quick_pick_sessions.c.user_b_id == b,
        )
    )
    existing = result.fetchone()
    if existing:
        return existing.id

    # Pick 5 random questions, trying to spread across categories
    result = await db.execute(select(quick_pick_questions))
    all_questions = result.fetchall()
    if len(all_questions) < 5:
        raise HTTPException(status_code=500, detail="Not enough quick pick questions seeded")

    # Group by category and pick one from each, then fill remainder randomly
    by_category: dict[str, list] = {}
    for q in all_questions:
        by_category.setdefault(q.category, []).append(q)

    selected_ids: list[int] = []
    categories = list(by_category.keys())
    random.shuffle(categories)
    for cat in categories:
        if len(selected_ids) >= 5:
            break
        pick = random.choice(by_category[cat])
        selected_ids.append(pick.id)

    # Fill remaining slots from unused questions
    if len(selected_ids) < 5:
        remaining = [q for q in all_questions if q.id not in selected_ids]
        random.shuffle(remaining)
        for q in remaining:
            if len(selected_ids) >= 5:
                break
            selected_ids.append(q.id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        result = await db.execute(
            insert(quick_pick_sessions).values(
                user_a_id=a,
                user_b_id=b,
                status="pending_both",
                questions=selected_ids,
                created_at=now,
            ).returning(quick_pick_sessions.c.id)
        )
        session_id = result.scalar_one()
    except IntegrityError:
        # Race condition: other request created the session first — fetch it
        await db.rollback()
        result = await db.execute(
            select(quick_pick_sessions.c.id).where(
                quick_pick_sessions.c.user_a_id == a,
                quick_pick_sessions.c.user_b_id == b,
            )
        )
        session_id = result.scalar_one()
    return session_id


async def _user_info(db: AsyncSession, user_id: int) -> dict:
    """Compact user info for match listings."""
    result = await db.execute(
        select(users.c.id, users.c.name, users.c.avatar_url)
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
        "vibe_labels": vibe_labels,
    }


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/interest/{user_id}")
async def express_interest(
    user_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Express interest in another user. If mutual, auto-creates a Quick Picks session."""
    me = await _resolve_user_id(db, payload)

    if me == user_id:
        raise HTTPException(status_code=400, detail="Cannot express interest in yourself")

    # Verify target user exists
    result = await db.execute(select(users.c.id).where(users.c.id == user_id))
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    # Check if already expressed interest
    result = await db.execute(
        select(interests.c.id).where(
            interests.c.from_user_id == me,
            interests.c.to_user_id == user_id,
        )
    )
    if result.fetchone():
        # Already expressed — check if mutual and return status
        result = await db.execute(
            select(interests.c.id).where(
                interests.c.from_user_id == user_id,
                interests.c.to_user_id == me,
            )
        )
        is_mutual = result.fetchone() is not None
        session_id = None
        if is_mutual:
            a, b = min(me, user_id), max(me, user_id)
            result = await db.execute(
                select(quick_pick_sessions.c.id).where(
                    quick_pick_sessions.c.user_a_id == a,
                    quick_pick_sessions.c.user_b_id == b,
                )
            )
            row = result.fetchone()
            session_id = row.id if row else None
        return {"mutual": is_mutual, "session_id": session_id}

    # Insert interest
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        insert(interests).values(
            from_user_id=me,
            to_user_id=user_id,
            created_at=now,
        )
    )

    # Check for reciprocal interest
    result = await db.execute(
        select(interests.c.id).where(
            interests.c.from_user_id == user_id,
            interests.c.to_user_id == me,
        )
    )
    if result.fetchone():
        session_id = await _create_session(db, me, user_id)
        await db.commit()

        # Notify both users: match_unlocked (supersedes wave_received)
        r1 = await db.execute(select(users.c.name).where(users.c.id == me))
        my_name = r1.scalar()
        r2 = await db.execute(select(users.c.name).where(users.c.id == user_id))
        other_name = r2.scalar()
        await create_notification(
            db, user_id, "match_unlocked", me,
            f"It's a match! Quick Picks unlocked with {my_name}",
            "Answer 5 quick questions to see how compatible you are",
            {"user_id": me},
        )
        await create_notification(
            db, me, "match_unlocked", user_id,
            f"It's a match! Quick Picks unlocked with {other_name}",
            "Answer 5 quick questions to see how compatible you are",
            {"user_id": user_id},
        )
        await db.commit()
        return {"mutual": True, "session_id": session_id}

    await db.commit()

    # Notify target: wave_received
    r = await db.execute(select(users.c.name).where(users.c.id == me))
    my_name = r.scalar()
    await create_notification(
        db, user_id, "wave_received", me,
        f"{my_name} waved at you!",
        "Tap to check out their apartment",
        {"user_id": me},
    )
    await db.commit()
    return {"mutual": False, "session_id": None}


@router.delete("/interest/{user_id}")
async def withdraw_interest(
    user_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Withdraw interest in another user.

    Deletes both directions (A→B and B→A) for a clean break — if they
    want to match again, both need to wave fresh. Also deletes any
    Quick Picks session between the pair (answers cascade-delete via FK).
    """
    me = await _resolve_user_id(db, payload)

    # Delete my interest in them
    result = await db.execute(
        delete(interests).where(
            interests.c.from_user_id == me,
            interests.c.to_user_id == user_id,
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="No interest to withdraw")

    # Delete their interest in me (clean break — both must re-wave to rematch)
    await db.execute(
        delete(interests).where(
            interests.c.from_user_id == user_id,
            interests.c.to_user_id == me,
        )
    )

    # Clean up the Quick Picks session for this pair (answers cascade-delete)
    a, b = min(me, user_id), max(me, user_id)
    await db.execute(
        delete(quick_pick_sessions).where(
            quick_pick_sessions.c.user_a_id == a,
            quick_pick_sessions.c.user_b_id == b,
        )
    )

    await db.commit()
    return {"detail": "Interest withdrawn"}


@router.get("/interest/sent")
async def list_sent_interests(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all user IDs the current user has waved at.

    Called once by the frontend to initialize wave button states
    across all neighbor cards without N+1 API calls.
    """
    me = await _resolve_user_id(db, payload)
    result = await db.execute(
        select(interests.c.to_user_id).where(interests.c.from_user_id == me)
    )
    return {"sent_to": [row.to_user_id for row in result.fetchall()]}


@router.get("/interest/mutual")
async def list_mutual_interests(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """List all mutual interests with Quick Picks session status.

    Powers the Matches tab — shows users who've mutually waved,
    along with the state of their Quick Picks session.
    """
    me = await _resolve_user_id(db, payload)

    # Find users who I've expressed interest in AND who've expressed interest in me
    i_sent = select(interests.c.to_user_id).where(interests.c.from_user_id == me)
    result = await db.execute(
        select(interests.c.from_user_id).where(
            interests.c.to_user_id == me,
            interests.c.from_user_id.in_(i_sent),
        )
    )
    mutual_ids = [row.from_user_id for row in result.fetchall()]

    matches = []
    for uid in mutual_ids:
        info = await _user_info(db, uid)
        if not info:
            continue

        # Get session status
        a, b = min(me, uid), max(me, uid)
        result = await db.execute(
            select(quick_pick_sessions.c.id, quick_pick_sessions.c.status, quick_pick_sessions.c.results_viewed_by).where(
                quick_pick_sessions.c.user_a_id == a,
                quick_pick_sessions.c.user_b_id == b,
            )
        )
        session = result.fetchone()
        if session:
            info["session_id"] = session.id
            info["session_status"] = session.status
            # Determine if the current user still needs to answer
            # pending_both = both need to answer, pending_a = user_a needs to answer, etc.
            status = session.status
            viewed_by = list(session.results_viewed_by or [])
            if status == "completed":
                # Action needed if user hasn't viewed results yet
                info["my_action_needed"] = (me not in viewed_by)
            elif status == "pending_both":
                info["my_action_needed"] = True
            elif status == "pending_a":
                info["my_action_needed"] = (me == a)
            elif status == "pending_b":
                info["my_action_needed"] = (me == b)
            else:
                info["my_action_needed"] = False
        else:
            info["session_id"] = None
            info["session_status"] = None
            info["my_action_needed"] = False

        matches.append(info)

    return {"matches": matches}


@router.get("/quickpicks/session/{user_id}")
async def get_session(
    user_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the Quick Picks session between current user and target user.

    Returns the 5 questions with full text plus the current user's answers so far.
    Does NOT reveal the other user's answers until both are done (privacy).
    """
    me = await _resolve_user_id(db, payload)
    a, b = min(me, user_id), max(me, user_id)

    result = await db.execute(
        select(quick_pick_sessions).where(
            quick_pick_sessions.c.user_a_id == a,
            quick_pick_sessions.c.user_b_id == b,
        )
    )
    session = result.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="No Quick Picks session found")

    # Fetch the actual question objects in one query
    question_ids = session.questions or []
    result = await db.execute(
        select(quick_pick_questions).where(quick_pick_questions.c.id.in_(question_ids))
    )
    q_by_id = {q.id: q for q in result.fetchall()}
    questions_data = []
    for qid in question_ids:
        q = q_by_id.get(qid)
        if q:
            questions_data.append({
                "id": q.id,
                "prompt": q.prompt,
                "option_a": q.option_a,
                "option_b": q.option_b,
                "category": q.category,
            })

    # Fetch current user's answers
    result = await db.execute(
        select(quick_pick_answers).where(
            quick_pick_answers.c.session_id == session.id,
            quick_pick_answers.c.user_id == me,
        ).order_by(quick_pick_answers.c.question_index)
    )
    my_answers = {}
    for row in result.fetchall():
        my_answers[row.question_index] = row.selected_option

    return {
        "session_id": session.id,
        "status": session.status,
        "questions": questions_data,
        "my_answers": my_answers,
    }


@router.post("/quickpicks/answer")
async def submit_answer(
    body: dict,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Record an answer to one Quick Picks question.

    After the answering user submits all 5, updates the session status:
    pending_both → pending_<other> if only one finished, completed if both done.
    """
    me = await _resolve_user_id(db, payload)

    session_id = body.get("session_id")
    question_index = body.get("question_index")
    selected_option = body.get("selected_option")

    if session_id is None or question_index is None or selected_option is None:
        raise HTTPException(status_code=400, detail="Missing required fields")

    if selected_option not in ("a", "b"):
        raise HTTPException(status_code=400, detail="selected_option must be 'a' or 'b'")

    if question_index < 0 or question_index > 4:
        raise HTTPException(status_code=400, detail="question_index must be 0-4")

    # Verify session exists and user is a participant
    result = await db.execute(
        select(quick_pick_sessions).where(quick_pick_sessions.c.id == session_id)
    )
    session = result.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if me not in (session.user_a_id, session.user_b_id):
        raise HTTPException(status_code=403, detail="Not a participant in this session")

    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")

    # Insert answer, do nothing if answer already exists (duplicate)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        pg_insert(quick_pick_answers).values(
            session_id=session_id,
            user_id=me,
            question_index=question_index,
            selected_option=selected_option,
            answered_at=now,
        ).on_conflict_do_nothing(index_elements=["session_id", "user_id", "question_index"])
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="Already answered this question")

    # Count this user's answers to determine if they've finished all 5
    result = await db.execute(
        select(func.count()).select_from(quick_pick_answers).where(
            quick_pick_answers.c.session_id == session_id,
            quick_pick_answers.c.user_id == me,
        )
    )
    my_count = result.scalar() or 0

    # Update session status if user has completed all 5
    if my_count >= 5:
        other_id = session.user_b_id if me == session.user_a_id else session.user_a_id
        result = await db.execute(
            select(func.count()).select_from(quick_pick_answers).where(
                quick_pick_answers.c.session_id == session_id,
                quick_pick_answers.c.user_id == other_id,
            )
        )
        other_count = result.scalar() or 0

        if other_count >= 5:
            new_status = "completed"
        else:
            # This user is done, waiting on the other
            if me == session.user_a_id:
                new_status = "pending_b"
            else:
                new_status = "pending_a"

        await db.execute(
            update(quick_pick_sessions)
            .where(quick_pick_sessions.c.id == session_id)
            .values(status=new_status)
        )

        # Notify the other user when session completes
        if new_status == "completed":
            r = await db.execute(select(users.c.name).where(users.c.id == me))
            my_name = r.scalar()
            await create_notification(
                db, other_id, "quickpicks_completed", me,
                f"Quick Picks results ready with {my_name}!",
                "See how your answers compare",
                {"session_id": session_id, "user_id": me},
            )

    await db.commit()
    return {"detail": "Answer recorded", "answers_submitted": my_count}


@router.get("/quickpicks/results/{session_id}")
async def get_results(
    session_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Side-by-side results for a completed Quick Picks session.

    Only available when both users have answered all 5 questions.
    Returns each question with both answers, agreement flag, and
    conversation starters for divergent answers.
    """
    me = await _resolve_user_id(db, payload)

    result = await db.execute(
        select(quick_pick_sessions).where(quick_pick_sessions.c.id == session_id)
    )
    session = result.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if me not in (session.user_a_id, session.user_b_id):
        raise HTTPException(status_code=403, detail="Not a participant in this session")

    if session.status != "completed":
        raise HTTPException(status_code=400, detail="Session not yet completed")

    # Mark results as viewed by this user so the badge clears
    viewed_by = list(session.results_viewed_by or [])
    if me not in viewed_by:
        viewed_by.append(me)
        await db.execute(
            update(quick_pick_sessions)
            .where(quick_pick_sessions.c.id == session_id)
            .values(results_viewed_by=viewed_by)
        )
        await db.commit()

    other_id = session.user_b_id if me == session.user_a_id else session.user_a_id

    # Fetch questions in one query
    question_ids = session.questions or []
    result = await db.execute(
        select(quick_pick_questions).where(quick_pick_questions.c.id.in_(question_ids))
    )
    questions_map: dict[int, dict] = {}
    for q in result.fetchall():
        questions_map[q.id] = {
            "prompt": q.prompt,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "category": q.category,
        }

    # Fetch all answers for both users
    result = await db.execute(
        select(quick_pick_answers).where(
            quick_pick_answers.c.session_id == session_id,
        ).order_by(quick_pick_answers.c.question_index)
    )
    all_answers = result.fetchall()

    my_answers: dict[int, str] = {}
    their_answers: dict[int, str] = {}
    for ans in all_answers:
        if ans.user_id == me:
            my_answers[ans.question_index] = ans.selected_option
        else:
            their_answers[ans.question_index] = ans.selected_option

    # Build comparison results
    comparisons = []
    agree_count = 0
    for idx, qid in enumerate(question_ids):
        q = questions_map.get(qid, {})
        my_choice = my_answers.get(idx)
        their_choice = their_answers.get(idx)
        agreed = my_choice == their_choice
        if agreed:
            agree_count += 1

        my_text = q.get(f"option_{my_choice}") if my_choice else None
        their_text = q.get(f"option_{their_choice}") if their_choice else None

        entry = {
            "prompt": q.get("prompt", ""),
            "category": q.get("category", ""),
            "my_choice": my_choice,
            "their_choice": their_choice,
            "my_text": my_text,
            "their_text": their_text,
            "agreed": agreed,
        }
        if not agreed:
            entry["conversation_starter"] = f"You picked different approaches to: {q.get('prompt', '')} — worth discussing!"

        comparisons.append(entry)

    # Other user info for display
    other_info = await _user_info(db, other_id)

    return {
        "session_id": session_id,
        "other_user": other_info,
        "summary": f"{agree_count}/{len(question_ids)}",
        "agree_count": agree_count,
        "total": len(question_ids),
        "comparisons": comparisons,
    }
