from fastapi import APIRouter, Depends, HTTPException
from app.deps import require_verified_user
from app.database import get_db
from app.models import scenarios, scenario_responses, daily_scenario_assignments
from app.security import now
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, and_, or_, func
from pydantic import BaseModel
from typing import Literal

MAX_ACTIVE_RESPONSES = 3
router = APIRouter(prefix="/scenarios", tags=["scenarios"])

class AnswerRequest(BaseModel): 
    scenario_id: int
    selected_option: Literal["a","b","c","d"]
    replace_scenario_id: int | None = None


async def _get_active_scenarios(db: AsyncSession, me: int) -> list[dict]:
    """
    Return a user's active answers, oldest first, with option ids resolved to text.

    Args:
        db: Database session.
        me: user's id.
    
    Returns:
        A list of response dicts.
    """
    result_answered = await db.execute(
        select(scenario_responses.c.scenario_id, scenario_responses.c.selected_option, 
               scenarios.c.prompt, scenarios.c.options)
        .select_from(scenario_responses.join(scenarios, scenario_responses.c.scenario_id == scenarios.c.id))
        .where(scenario_responses.c.user_id == me, scenario_responses.c.active.is_(True))
        .order_by(scenario_responses.c.answered_at)
    )
    rows = result_answered.fetchall()

    current_responses = []
    for r in rows:
        selected_text = None
        for opt in r.options:
            if opt["id"] == r.selected_option:
                selected_text = opt["text"]
                break
        current_response = {
            "scenario_id": r.scenario_id,
            "prompt": r.prompt,
            "selected_text": selected_text
        }
        current_responses.append(current_response)

    return current_responses


@router.get("/daily")
async def get_daily(
    me: int = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Gets/Assigns user's daily scenario. Returns the scenario assigned + a list of dicts with user's active scenarios.

    - If no daily scenario is assigned, picks one from unanswered scenarios.
    - If no unanaswered scenarios exist picks the oldest answered scenario.
    """

    # Check if today's scenario has been assigned
    result_assigned = await db.execute(
        select(daily_scenario_assignments)
        .where(daily_scenario_assignments.c.user_id == me, daily_scenario_assignments.c.assigned_date == now().date())
    )
    assigned = result_assigned.fetchone()

    if not assigned:
        # Selects scenario_id. For further explanation how this call works refer to notes "The abominable call".
        result = await db.execute(
            select(scenarios.c.id)
            .outerjoin(scenario_responses, and_(
                scenarios.c.id == scenario_responses.c.scenario_id,     # how the rows match
                scenario_responses.c.user_id == me                      # which rows are allowed to match
            ))
            .where(or_(scenario_responses.c.answered_at.is_(None), scenario_responses.c.active.is_(False)))     # never answered row has answered_at as NULL
            .order_by(scenario_responses.c.answered_at.asc().nulls_first(), func.random())      # order by answered ascending, nulls first, then randomize the nulls
            .limit(1)
        )
        scenario_to_insert = result.fetchone()

        # Assign the scenario
        result = await db.execute(
            insert(daily_scenario_assignments)
            .values(
                user_id=me,
                scenario_id=scenario_to_insert.id,
                assigned_date=now().date(),
            )
            .returning(daily_scenario_assignments.c.scenario_id, daily_scenario_assignments.c.completed)
        )
        assigned = result.fetchone()
        await db.commit()

    # Get scenario
    result = await db.execute(
        select(scenarios.c.id, scenarios.c.prompt, scenarios.c.options)
        .where(scenarios.c.id == assigned.scenario_id)
    )
    row = result.fetchone()
    scenario = {
        "id": row.id,
        "prompt": row.prompt,
        "options": row.options
    }

    current_responses = await _get_active_scenarios(db, me)
    requires_substitution = len(current_responses) >= MAX_ACTIVE_RESPONSES

    return {
        "scenario": scenario,
        "completed_today": assigned.completed,
        "requires_substitution": requires_substitution,
        "current_responses": current_responses
    }

@router.post("/answer")
async def answer_scenario(
    body: AnswerRequest,
    me: int = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Records user's answer to today's assigned scenario.

    - At MAX_ACTIVE_RESPONSES must include `replace_scenario_id`, naming one of them to retire.
    - raises 400: nothing assigned today, `replace_scenario_id` is missing, invalid, or sent below the limit.
    - raises 409: not today's scenario, today's scenario was already answered.
    """
    # Check that scenario_id matches the one assigned & that user is not answering the same scenario twice.
    result = await db.execute(
        select(daily_scenario_assignments.c.scenario_id, daily_scenario_assignments.c.completed)
        .where(daily_scenario_assignments.c.user_id == me, daily_scenario_assignments.c.assigned_date == now().date())
    )
    assigned = result.fetchone()
    if not assigned:
        raise HTTPException(status_code=400, detail="Daily scenario is not assigned.")
    elif assigned.scenario_id != body.scenario_id:
        raise HTTPException(status_code=409, detail="Can't answer a scenario other than the one assigned.")
    if assigned.completed == True:
        raise HTTPException(status_code=409, detail="Daily scenario has already been answered.")

    # Check that passed replace_scenario_id is present if user has three responses.
    result = await db.execute(
        select(scenarios.c.id)
        .select_from(scenario_responses.join(scenarios, scenarios.c.id == scenario_responses.c.scenario_id))
        .where(scenario_responses.c.user_id == me, scenario_responses.c.active.is_(True))
    )
    active_ids = [row.id for row in result.fetchall()]
    if not body.replace_scenario_id and len(active_ids) >= MAX_ACTIVE_RESPONSES:
        raise HTTPException(status_code=400, detail="Need replace_scenario_id when user has 3 active responses.")

    # Check if we're recycling a scenario: a case where user has answered all scenarios and /daily assigns the oldest scenario answered.
    result = await db.execute(
        select(scenario_responses.c.id)
        .where(scenario_responses.c.user_id == me, scenario_responses.c.scenario_id == body.scenario_id)
    )
    recycle = result.fetchone() is not None

    if body.replace_scenario_id is not None:
        if body.replace_scenario_id not in active_ids:
            raise HTTPException(status_code=400, detail="scenario_id to be replaced doesn't match any existing active scenario_ids")
        elif len(active_ids) < MAX_ACTIVE_RESPONSES:
            raise HTTPException(status_code=400, detail=f"Can't pass replace_scenario_id when current response limit is not reached: ({len(active_ids)}/3)")

        # Update the active column of id to be replaced to false.
        await db.execute(
            update(scenario_responses)
            .where(scenario_responses.c.user_id == me, scenario_responses.c.scenario_id == body.replace_scenario_id)
            .values(active = False)
        )

    # If it's a recycled scenario we need to update existing scenario rather than inserting.
    if recycle:
        await db.execute(
            update(scenario_responses)
            .where(scenario_responses.c.scenario_id == body.scenario_id, scenario_responses.c.user_id == me)
            .values(
                selected_option = body.selected_option,
                answered_at = now(),
                active = True,
            )
        )
    else:
        # Insert the new scenario as active
        await db.execute(
            insert(scenario_responses)
            .values(
                user_id = me,
                scenario_id = body.scenario_id,
                selected_option = body.selected_option,
                answered_at = now(),
                active = True,
            )
        )
    await db.execute(
        update(daily_scenario_assignments)
        .where(daily_scenario_assignments.c.user_id == me, daily_scenario_assignments.c.assigned_date == now().date())
        .values(completed = True)
    )
    await db.commit()

    return {"detail": "Answer has been recorded."}

@router.post("/skip")
async def skip_scenario(
    me: int = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    - Skips daily scenario by marking it as completed.
    """
    await db.execute(
        update(daily_scenario_assignments)
        .where(daily_scenario_assignments.c.user_id == me, daily_scenario_assignments.c.assigned_date == now().date())
        .values(completed = True)
    )
    await db.commit()

    return {"detail": "Scenario has been skipped."}

@router.get("/history/{user_id}")
async def history_scenarios(
    user_id: int,
    me: int = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Takes user_id and returns their current responses. Returns an empty list if user does not exist.
    
    - "me" is unused, but kept for verification purposes.
    """
    current_responses = await _get_active_scenarios(db, user_id)

    return {
        "responses": current_responses
    }