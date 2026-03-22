from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from app.database import get_db
from app.models import (
    users,
    furniture_catalog,
    room_style_presets,
    apartments,
    apartment_items,
)
from app.deps import get_current_user
from pydantic import BaseModel
from datetime import datetime, timezone
from collections import defaultdict

router = APIRouter(prefix="/apartments", tags=["apartments"])


# ── Request schemas ──────────────────────────────────────────────

class ApplyPresetRequest(BaseModel):
    preset_id: int

class PlaceItemRequest(BaseModel):
    furniture_id: int
    zone: str
    position_x: float = 0
    position_y: float = 0


# ── Helpers ──────────────────────────────────────────────────────

async def _get_or_404_apartment(db: AsyncSession, user_id: int):
    """Return the apartment row for a user, or raise 404."""
    result = await db.execute(
        select(apartments).where(apartments.c.user_id == user_id)
    )
    apt = result.fetchone()
    if not apt:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return apt


async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    """Get the users.id from the JWT email claim."""
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id


async def _apartment_with_items(db: AsyncSession, apt):
    """Return a dict of an apartment plus its placed items."""
    items_result = await db.execute(
        select(apartment_items).where(
            apartment_items.c.apartment_id == apt.id
        )
    )
    items = [dict(r._mapping) for r in items_result.fetchall()]
    return {
        "id": apt.id,
        "user_id": apt.user_id,
        "created_at": apt.created_at.isoformat() if apt.created_at else None,
        "updated_at": apt.updated_at.isoformat() if apt.updated_at else None,
        "items": items,
    }


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/catalog")
async def get_catalog(db: AsyncSession = Depends(get_db)):
    """All furniture grouped by zone → category."""
    result = await db.execute(select(furniture_catalog))
    rows = [dict(r._mapping) for r in result.fetchall()]

    grouped: dict = defaultdict(lambda: defaultdict(list))
    for item in rows:
        grouped[item["zone"]][item["category"]].append(item)
    return dict(grouped)


@router.get("/presets")
async def get_presets(db: AsyncSession = Depends(get_db)):
    """All style presets grouped by zone."""
    result = await db.execute(select(room_style_presets))
    rows = [dict(r._mapping) for r in result.fetchall()]

    grouped: dict = defaultdict(list)
    for preset in rows:
        grouped[preset["zone"]].append(preset)
    return dict(grouped)


@router.post("/")
async def create_apartment(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an apartment for the current user (idempotent)."""
    user_id = await _resolve_user_id(db, payload)

    # Return existing apartment if one already exists
    result = await db.execute(
        select(apartments).where(apartments.c.user_id == user_id)
    )
    existing = result.fetchone()
    if existing:
        return await _apartment_with_items(db, existing)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        insert(apartments).values(
            user_id=user_id, created_at=now, updated_at=now
        )
    )
    await db.commit()

    result = await db.execute(
        select(apartments).where(apartments.c.user_id == user_id)
    )
    apt = result.fetchone()
    return await _apartment_with_items(db, apt)


@router.post("/apply-preset")
async def apply_preset(
    body: ApplyPresetRequest,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a style preset to a zone — replaces all items in that zone."""
    user_id = await _resolve_user_id(db, payload)
    apt = await _get_or_404_apartment(db, user_id)

    # Fetch the preset
    result = await db.execute(
        select(room_style_presets).where(room_style_presets.c.id == body.preset_id)
    )
    preset = result.fetchone()
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")

    zone = preset.zone
    furniture_ids = preset.furniture_ids or []

    # Remove existing items in this zone
    await db.execute(
        delete(apartment_items).where(
            apartment_items.c.apartment_id == apt.id,
            apartment_items.c.zone == zone,
        )
    )

    # Insert preset furniture
    for fid in furniture_ids:
        await db.execute(
            insert(apartment_items).values(
                apartment_id=apt.id,
                furniture_id=fid,
                zone=zone,
                position_x=0,
                position_y=0,
            )
        )

    # Update apartment timestamp
    from sqlalchemy import update
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        update(apartments)
        .where(apartments.c.id == apt.id)
        .values(updated_at=now)
    )
    await db.commit()

    # Re-fetch and return
    result = await db.execute(
        select(apartments).where(apartments.c.id == apt.id)
    )
    apt = result.fetchone()
    return await _apartment_with_items(db, apt)


@router.get("/me")
async def get_my_apartment(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's apartment + placed items."""
    user_id = await _resolve_user_id(db, payload)
    apt = await _get_or_404_apartment(db, user_id)
    return await _apartment_with_items(db, apt)


@router.get("/{user_id}")
async def get_user_apartment(
    user_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """View another user's apartment."""
    apt = await _get_or_404_apartment(db, user_id)
    return await _apartment_with_items(db, apt)


@router.post("/items")
async def place_item(
    body: PlaceItemRequest,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a furniture item. Enforces constraint groups within a zone."""
    user_id = await _resolve_user_id(db, payload)
    apt = await _get_or_404_apartment(db, user_id)

    # Validate the furniture item exists
    result = await db.execute(
        select(furniture_catalog).where(furniture_catalog.c.id == body.furniture_id)
    )
    furniture = result.fetchone()
    if not furniture:
        raise HTTPException(status_code=404, detail="Furniture item not found")

    # Prevent placing the same furniture twice in the same zone
    result = await db.execute(
        select(apartment_items).where(
            apartment_items.c.apartment_id == apt.id,
            apartment_items.c.furniture_id == body.furniture_id,
            apartment_items.c.zone == body.zone,
        )
    )
    if result.fetchone():
        raise HTTPException(status_code=409, detail="This item is already placed in this zone")

    # Enforce constraint group: remove conflicting item in same zone
    if furniture.constraint_group:
        # Find all furniture IDs in the same constraint group
        result = await db.execute(
            select(furniture_catalog.c.id).where(
                furniture_catalog.c.constraint_group == furniture.constraint_group
            )
        )
        conflicting_ids = [r.id for r in result.fetchall()]

        await db.execute(
            delete(apartment_items).where(
                apartment_items.c.apartment_id == apt.id,
                apartment_items.c.zone == body.zone,
                apartment_items.c.furniture_id.in_(conflicting_ids),
            )
        )

    await db.execute(
        insert(apartment_items).values(
            apartment_id=apt.id,
            furniture_id=body.furniture_id,
            zone=body.zone,
            position_x=body.position_x,
            position_y=body.position_y,
        )
    )

    # Update apartment timestamp
    from sqlalchemy import update
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        update(apartments)
        .where(apartments.c.id == apt.id)
        .values(updated_at=now)
    )
    await db.commit()

    result = await db.execute(
        select(apartments).where(apartments.c.id == apt.id)
    )
    apt = result.fetchone()
    return await _apartment_with_items(db, apt)


@router.delete("/items/{item_id}")
async def remove_item(
    item_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a placed item. Must belong to the current user's apartment."""
    user_id = await _resolve_user_id(db, payload)
    apt = await _get_or_404_apartment(db, user_id)

    # Verify item belongs to this apartment
    result = await db.execute(
        select(apartment_items).where(
            apartment_items.c.id == item_id,
            apartment_items.c.apartment_id == apt.id,
        )
    )
    item = result.fetchone()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in your apartment")

    await db.execute(
        delete(apartment_items).where(apartment_items.c.id == item_id)
    )

    # Update apartment timestamp
    from sqlalchemy import update
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute(
        update(apartments)
        .where(apartments.c.id == apt.id)
        .values(updated_at=now)
    )
    await db.commit()

    return {"detail": "Item removed"}
