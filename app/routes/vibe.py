from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete
from app.database import get_db
from app.models import (
    users,
    apartments,
    apartment_items,
    furniture_catalog,
    preference_profiles,
)
from app.deps import require_verified_user
from app.vibe_engine import calculate_weights, weights_to_labels, compare_profiles
from datetime import datetime, timezone

router = APIRouter(prefix="/vibe", tags=["vibe"])


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id


async def recalculate_vibe(db: AsyncSession, user_id: int, *, commit: bool = True) -> dict:
    """
    Recalculate a user's vibe profile from their placed apartment items.
    Upserts the preference_profiles row. Returns the profile dict.
    """
    # Get the user's apartment
    result = await db.execute(
        select(apartments.c.id).where(apartments.c.user_id == user_id)
    )
    apt = result.fetchone()
    if not apt:
        return {"user_id": user_id, "weights": {}, "vibe_labels": [], "updated_at": None}

    # Fetch placed items with their furniture catalog weights
    result = await db.execute(
        select(furniture_catalog.c.preference_weights).where(
            furniture_catalog.c.id.in_(
                select(apartment_items.c.furniture_id).where(
                    apartment_items.c.apartment_id == apt.id
                )
            )
        )
    )
    items = [{"preference_weights": row.preference_weights} for row in result.fetchall()]

    weights = calculate_weights(items)
    labels = weights_to_labels(weights)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Upsert preference_profiles
    existing = await db.execute(
        select(preference_profiles).where(
            preference_profiles.c.user_id == user_id
        )
    )
    if existing.fetchone():
        await db.execute(
            update(preference_profiles)
            .where(preference_profiles.c.user_id == user_id)
            .values(weights=weights, vibe_labels=labels, updated_at=now)
        )
    else:
        await db.execute(
            insert(preference_profiles).values(
                user_id=user_id, weights=weights, vibe_labels=labels, updated_at=now
            )
        )
    if commit:
        await db.commit()

    return {
        "user_id": user_id,
        "weights": weights,
        "vibe_labels": labels,
        "updated_at": now.isoformat(),
    }


async def _get_profile(db: AsyncSession, user_id: int) -> dict:
    """Get a user's vibe profile, recalculating if it doesn't exist."""
    result = await db.execute(
        select(preference_profiles).where(
            preference_profiles.c.user_id == user_id
        )
    )
    row = result.fetchone()
    if row:
        return {
            "user_id": row.user_id,
            "weights": row.weights or {},
            "vibe_labels": row.vibe_labels or [],
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    # No profile yet — calculate it
    return await recalculate_vibe(db, user_id)


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/me")
async def get_my_vibe(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's vibe profile. Recalculates if stale or missing."""
    user_id = await _resolve_user_id(db, payload)
    return await _get_profile(db, user_id)


@router.get("/compare/{user_id}")
async def compare_vibe(
    user_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare current user's vibe with another user's."""
    my_user_id = await _resolve_user_id(db, payload)
    if my_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot compare with yourself")

    my_profile = await _get_profile(db, my_user_id)
    their_profile = await _get_profile(db, user_id)

    comparison = compare_profiles(
        my_profile["weights"],
        their_profile["weights"],
    )

    return {
        "my_vibe": my_profile,
        "their_vibe": their_profile,
        **comparison,
    }


@router.get("/{user_id}")
async def get_user_vibe(
    user_id: int,
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Another user's vibe profile."""
    # Verify user exists
    result = await db.execute(select(users.c.id).where(users.c.id == user_id))
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
    return await _get_profile(db, user_id)


@router.post("/recalculate")
async def force_recalculate(
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Force recalculation of current user's vibe profile."""
    user_id = await _resolve_user_id(db, payload)
    return await recalculate_vibe(db, user_id)
