from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete, func
from app.database import get_db
from app.models import (
    users,
    scenarios,
    scenario_responses,
    daily_scenario_assignments,
)
from app.deps import get_current_user
from pydantic import BaseModel
from datetime import datetime, timezone, date
from typing import Optional

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

MAX_ACTIVE_RESPONSES = 3


# ── Request schemas ──────────────────────────────────────────────

class AnswerRequest(BaseModel):
    scenario_id: int
    selected_option: str
    replace_scenario_id: Optional[int] = None


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id


async def _get_current_responses(db: AsyncSession, user_id: int) -> list[dict]:
    """Get the user's current scenario responses with scenario details."""
    result = await db.execute(
        select(
            scenario_responses.c.id,
            scenario_responses.c.scenario_id,
            scenario_responses.c.selected_option,
            scenario_responses.c.answered_at,
            scenarios.c.prompt,
            scenarios.c.options,
        )
        .join(scenarios, scenario_responses.c.scenario_id == scenarios.c.id)
        .where(
            scenario_responses.c.user_id == user_id,
            scenario_responses.c.active == True,
        )
        .order_by(scenario_responses.c.answered_at.asc())
    )
    rows = result.fetchall()

    responses = []
    for row in rows:
        options = row.options or []
        selected_text = None
        for opt in options:
            if opt["id"] == row.selected_option:
                selected_text = opt["text"]
                break

        responses.append({
            "response_id": row.id,
            "scenario_id": row.scenario_id,
            "prompt": row.prompt,
            "options": options,
            "selected_option": row.selected_option,
            "selected_text": selected_text,
            "answered_at": row.answered_at.isoformat() if row.answered_at else None,
        })

    return responses


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/daily")
async def get_daily_scenario(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get today's scenario for the current user.
    Auto-assigns an unanswered scenario if none assigned for today.

    If user has >= 3 responses, returns requires_substitution=True along
    with their current responses so they can pick which to replace.
    """
    user_id = await _resolve_user_id(db, payload)
    today = date.today()

    current_responses = await _get_current_responses(db, user_id)
    response_count = len(current_responses)
    requires_substitution = response_count >= MAX_ACTIVE_RESPONSES

    # Check for an existing assignment today
    result = await db.execute(
        select(daily_scenario_assignments).where(
            daily_scenario_assignments.c.user_id == user_id,
            daily_scenario_assignments.c.assigned_date == today,
        )
    )
    assignment = result.fetchone()

    if assignment:
        if assignment.completed:
            return {
                "scenario": None,
                "completed_today": True,
                "response_count": response_count,
                "requires_substitution": False,
                "current_responses": current_responses,
            }
        # Fetch the assigned scenario
        result = await db.execute(
            select(scenarios).where(scenarios.c.id == assignment.scenario_id)
        )
        scenario = result.fetchone()
        if scenario:
            return {
                "scenario": _format_scenario(scenario),
                "completed_today": False,
                "response_count": response_count,
                "requires_substitution": requires_substitution,
                "current_responses": current_responses if requires_substitution else [],
            }

    # No assignment today — pick a random scenario the user hasn't answered
    # Exclude both current responses AND any previously answered-then-replaced
    answered_subq = (
        select(scenario_responses.c.scenario_id)
        .where(scenario_responses.c.user_id == user_id)
    )
    result = await db.execute(
        select(scenarios)
        .where(
            scenarios.c.active == True,
            scenarios.c.id.notin_(answered_subq),
        )
        .order_by(func.random())
        .limit(1)
    )
    scenario = result.fetchone()

    if not scenario:
        return {
            "scenario": None,
            "completed_today": False,
            "all_answered": True,
            "response_count": response_count,
            "requires_substitution": False,
            "current_responses": current_responses,
        }

    # Create today's assignment
    await db.execute(
        insert(daily_scenario_assignments).values(
            user_id=user_id,
            scenario_id=scenario.id,
            assigned_date=today,
            completed=False,
        )
    )
    await db.commit()

    return {
        "scenario": _format_scenario(scenario),
        "completed_today": False,
        "response_count": response_count,
        "requires_substitution": requires_substitution,
        "current_responses": current_responses if requires_substitution else [],
    }


@router.post("/answer")
async def answer_scenario(
    body: AnswerRequest,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Record the user's answer to a scenario.

    If user already has 3 responses, replace_scenario_id must be provided
    to specify which existing response to remove.
    """
    user_id = await _resolve_user_id(db, payload)

    # Validate scenario exists
    result = await db.execute(
        select(scenarios).where(scenarios.c.id == body.scenario_id)
    )
    scenario = result.fetchone()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Validate option exists
    options = scenario.options or []
    valid_ids = [o["id"] for o in options]
    if body.selected_option not in valid_ids:
        raise HTTPException(status_code=400, detail="Invalid option")

    # Check for duplicate response
    result = await db.execute(
        select(scenario_responses).where(
            scenario_responses.c.user_id == user_id,
            scenario_responses.c.scenario_id == body.scenario_id,
        )
    )
    if result.fetchone():
        raise HTTPException(status_code=409, detail="Already answered this scenario")

    # Check current active response count
    result = await db.execute(
        select(func.count())
        .select_from(scenario_responses)
        .where(
            scenario_responses.c.user_id == user_id,
            scenario_responses.c.active == True,
        )
    )
    count = result.scalar()

    if count >= MAX_ACTIVE_RESPONSES:
        if body.replace_scenario_id is None:
            raise HTTPException(
                status_code=400,
                detail="You have 3 active responses. Provide replace_scenario_id to swap one out.",
            )
        # Deactivate the response being replaced
        result = await db.execute(
            update(scenario_responses)
            .where(
                scenario_responses.c.user_id == user_id,
                scenario_responses.c.scenario_id == body.replace_scenario_id,
                scenario_responses.c.active == True,
            )
            .values(active=False)
        )
        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Response to replace not found",
            )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Record the new response
    await db.execute(
        insert(scenario_responses).values(
            user_id=user_id,
            scenario_id=body.scenario_id,
            selected_option=body.selected_option,
            answered_at=now,
        )
    )

    # Mark daily assignment as completed
    today = date.today()
    await db.execute(
        update(daily_scenario_assignments)
        .where(
            daily_scenario_assignments.c.user_id == user_id,
            daily_scenario_assignments.c.scenario_id == body.scenario_id,
            daily_scenario_assignments.c.assigned_date == today,
        )
        .values(completed=True)
    )

    await db.commit()

    return {"detail": "Answer recorded", "scenario_id": body.scenario_id}


@router.post("/skip")
async def skip_scenario(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Skip today's scenario without answering (keep current 3 responses).
    Marks today's daily assignment as completed.
    """
    user_id = await _resolve_user_id(db, payload)
    today = date.today()

    result = await db.execute(
        update(daily_scenario_assignments)
        .where(
            daily_scenario_assignments.c.user_id == user_id,
            daily_scenario_assignments.c.assigned_date == today,
        )
        .values(completed=True)
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="No scenario assigned today")

    await db.commit()

    return {"detail": "Scenario skipped"}


@router.get("/history")
async def get_history(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's active scenario responses (max 3)."""
    user_id = await _resolve_user_id(db, payload)
    responses = await _get_current_responses(db, user_id)
    return {"responses": responses}


@router.get("/compare/{user_id}")
async def compare_scenarios(
    user_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Compare scenario answers with another user.
    Only returns scenarios both users have answered (slow reveal).
    """
    my_user_id = await _resolve_user_id(db, payload)
    if my_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot compare with yourself")

    # Get my active responses
    result = await db.execute(
        select(scenario_responses.c.scenario_id, scenario_responses.c.selected_option)
        .where(
            scenario_responses.c.user_id == my_user_id,
            scenario_responses.c.active == True,
        )
    )
    my_responses = {row.scenario_id: row.selected_option for row in result.fetchall()}

    # Get their active responses
    result = await db.execute(
        select(scenario_responses.c.scenario_id, scenario_responses.c.selected_option)
        .where(
            scenario_responses.c.user_id == user_id,
            scenario_responses.c.active == True,
        )
    )
    their_responses = {row.scenario_id: row.selected_option for row in result.fetchall()}

    # Find shared scenarios
    shared_ids = set(my_responses.keys()) & set(their_responses.keys())
    if not shared_ids:
        return {"comparisons": [], "shared_count": 0}

    # Fetch scenario details
    result = await db.execute(
        select(scenarios).where(scenarios.c.id.in_(shared_ids))
    )
    scenario_map = {row.id: row for row in result.fetchall()}

    comparisons = []
    for sid in shared_ids:
        scenario = scenario_map.get(sid)
        if not scenario:
            continue

        options = scenario.options or []
        my_option = my_responses[sid]
        their_option = their_responses[sid]

        my_text = None
        their_text = None
        for opt in options:
            if opt["id"] == my_option:
                my_text = opt["text"]
            if opt["id"] == their_option:
                their_text = opt["text"]

        agreed = my_option == their_option
        conversation_starter = None
        if not agreed:
            conversation_starter = (
                "You answered differently on this one — "
                "great chance to share your perspectives!"
            )

        comparisons.append({
            "scenario_id": sid,
            "prompt": scenario.prompt,
            "my_answer": my_text,
            "their_answer": their_text,
            "agreed": agreed,
            "conversation_starter": conversation_starter,
        })

    return {
        "comparisons": comparisons,
        "shared_count": len(comparisons),
    }


def _format_scenario(scenario) -> dict:
    """Format a scenario row for API response."""
    return {
        "id": scenario.id,
        "prompt": scenario.prompt,
        "options": scenario.options or [],
    }
