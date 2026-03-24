from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete, func
from app.database import get_db
from app.models import (
    users,
    preference_profiles,
    neighborhoods,
    neighborhood_members,
    apartment_items,
    apartments,
    furniture_catalog,
    scenarios,
    scenario_responses,
)
from app.deps import get_current_user
from app.clustering import (
    kmeans_cluster,
    euclidean_distance,
    DEFAULT_K,
    NEW_ARRIVALS_NAME,
    NEW_ARRIVALS_DESC,
)
from app.vibe_engine import DIMENSIONS, weights_to_labels
from datetime import datetime, timezone, timedelta
import asyncio

router = APIRouter(prefix="/discovery", tags=["discovery"])

STALE_HOURS = 24
_clustering_lock = asyncio.Lock()


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_user_id(db: AsyncSession, payload: dict) -> int:
    email = payload["email"]
    result = await db.execute(select(users.c.id).where(users.c.email == email))
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row.id


async def _run_clustering(db: AsyncSession) -> None:
    """Run full clustering and persist results."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Fetch all preference profiles
    result = await db.execute(
        select(preference_profiles.c.user_id, preference_profiles.c.weights)
        .where(preference_profiles.c.weights.isnot(None))
    )
    profiles = [(row.user_id, row.weights) for row in result.fetchall()]

    # Find users with no profile (no apartment built)
    profiled_ids = {uid for uid, _ in profiles}
    result = await db.execute(select(users.c.id))
    all_user_ids = [row.id for row in result.fetchall()]
    no_profile_ids = [uid for uid in all_user_ids if uid not in profiled_ids]

    # Clear existing neighborhoods + members
    await db.execute(delete(neighborhood_members))
    await db.execute(delete(neighborhoods))

    # Cluster profiled users
    clusters = kmeans_cluster(profiles, k=DEFAULT_K)

    neighborhood_id_map: dict[int, int] = {}  # cluster_idx -> neighborhood_id

    for idx, cluster in enumerate(clusters):
        result = await db.execute(
            insert(neighborhoods).values(
                name=cluster["name"],
                centroid=cluster["centroid"],
                vibe_description=cluster["vibe_description"],
                updated_at=now,
            ).returning(neighborhoods.c.id)
        )
        n_id = result.scalar_one()
        neighborhood_id_map[idx] = n_id

        for user_id, sim_score in cluster["members"]:
            await db.execute(
                insert(neighborhood_members).values(
                    user_id=user_id,
                    neighborhood_id=n_id,
                    similarity_score=sim_score,
                    assigned_at=now,
                )
            )

    # Create "New Arrivals" for users without profiles
    if no_profile_ids:
        result = await db.execute(
            insert(neighborhoods).values(
                name=NEW_ARRIVALS_NAME,
                centroid={d: 0.0 for d in DIMENSIONS},
                vibe_description=NEW_ARRIVALS_DESC,
                updated_at=now,
            ).returning(neighborhoods.c.id)
        )
        new_arrivals_id = result.scalar_one()

        for uid in no_profile_ids:
            await db.execute(
                insert(neighborhood_members).values(
                    user_id=uid,
                    neighborhood_id=new_arrivals_id,
                    similarity_score=0.0,
                    assigned_at=now,
                )
            )

    await db.commit()


async def _ensure_clustering(db: AsyncSession, user_id: int) -> None:
    """Trigger re-clustering if the user has no assignment or it's stale."""
    result = await db.execute(
        select(neighborhood_members.c.assigned_at)
        .where(neighborhood_members.c.user_id == user_id)
    )
    row = result.fetchone()

    needs_recluster = False
    if not row:
        needs_recluster = True
    else:
        age = datetime.now(timezone.utc).replace(tzinfo=None) - row.assigned_at
        if age > timedelta(hours=STALE_HOURS):
            needs_recluster = True

    if needs_recluster:
        async with _clustering_lock:
            # Re-check after acquiring lock (another request may have just finished)
            result = await db.execute(
                select(neighborhood_members.c.assigned_at)
                .where(neighborhood_members.c.user_id == user_id)
            )
            row = result.fetchone()
            if row:
                age = datetime.now(timezone.utc).replace(tzinfo=None) - row.assigned_at
                if age <= timedelta(hours=STALE_HOURS):
                    return
            await _run_clustering(db)


async def _user_summary(db: AsyncSession, user_id: int) -> dict:
    """Build a compact user summary dict for neighbor listings."""
    result = await db.execute(
        select(users.c.id, users.c.name, users.c.avatar_url)
        .where(users.c.id == user_id)
    )
    u = result.fetchone()
    if not u:
        return {}

    # Vibe labels
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

@router.get("/neighborhood")
async def get_my_neighborhood(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Current user's neighborhood: name, vibe_description, and list of neighbors.
    Triggers re-clustering if assignment is missing or stale (>24h).
    """
    user_id = await _resolve_user_id(db, payload)
    await _ensure_clustering(db, user_id)

    # Get user's neighborhood
    result = await db.execute(
        select(
            neighborhood_members.c.neighborhood_id,
            neighborhood_members.c.similarity_score,
        ).where(neighborhood_members.c.user_id == user_id)
    )
    membership = result.fetchone()
    if not membership:
        raise HTTPException(status_code=404, detail="No neighborhood assignment found")

    # Get neighborhood info
    result = await db.execute(
        select(neighborhoods).where(neighborhoods.c.id == membership.neighborhood_id)
    )
    hood = result.fetchone()
    if not hood:
        raise HTTPException(status_code=404, detail="Neighborhood not found")

    # Get all members
    result = await db.execute(
        select(
            neighborhood_members.c.user_id,
            neighborhood_members.c.similarity_score,
        ).where(
            neighborhood_members.c.neighborhood_id == membership.neighborhood_id,
        )
    )
    member_rows = result.fetchall()

    neighbors = []
    for mr in member_rows:
        if mr.user_id == user_id:
            continue
        summary = await _user_summary(db, mr.user_id)
        if summary:
            summary["similarity_score"] = mr.similarity_score
            neighbors.append(summary)

    # Sort by similarity descending
    neighbors.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)

    return {
        "neighborhood": {
            "id": hood.id,
            "name": hood.name,
            "vibe_description": hood.vibe_description,
        },
        "my_similarity_score": membership.similarity_score,
        "neighbors": neighbors,
    }


@router.get("/nearby")
async def get_nearby_neighborhoods(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    2–3 neighboring clusters by centroid distance for exploration.
    Returns name, vibe_description, member_count, sample members.
    """
    user_id = await _resolve_user_id(db, payload)
    await _ensure_clustering(db, user_id)

    # Get user's neighborhood
    result = await db.execute(
        select(neighborhood_members.c.neighborhood_id)
        .where(neighborhood_members.c.user_id == user_id)
    )
    my_membership = result.fetchone()
    if not my_membership:
        return {"nearby": []}

    my_hood_id = my_membership.neighborhood_id

    # Get my neighborhood's centroid
    result = await db.execute(
        select(neighborhoods.c.centroid).where(neighborhoods.c.id == my_hood_id)
    )
    my_hood = result.fetchone()
    if not my_hood or not my_hood.centroid:
        return {"nearby": []}

    my_centroid = my_hood.centroid

    # Get all other neighborhoods
    result = await db.execute(
        select(neighborhoods).where(neighborhoods.c.id != my_hood_id)
    )
    other_hoods = result.fetchall()

    # Sort by distance to my centroid
    scored = []
    for h in other_hoods:
        dist = euclidean_distance(my_centroid, h.centroid or {})
        scored.append((h, dist))
    scored.sort(key=lambda x: x[1])

    nearby = []
    for h, dist in scored[:3]:
        # Count members
        result = await db.execute(
            select(func.count())
            .select_from(neighborhood_members)
            .where(neighborhood_members.c.neighborhood_id == h.id)
        )
        member_count = result.scalar() or 0

        # Sample members (up to 3)
        result = await db.execute(
            select(neighborhood_members.c.user_id, neighborhood_members.c.similarity_score)
            .where(neighborhood_members.c.neighborhood_id == h.id)
            .order_by(neighborhood_members.c.similarity_score.desc())
            .limit(3)
        )
        sample_rows = result.fetchall()
        sample_members = []
        for sr in sample_rows:
            summary = await _user_summary(db, sr.user_id)
            if summary:
                summary["similarity_score"] = sr.similarity_score
                sample_members.append(summary)

        nearby.append({
            "id": h.id,
            "name": h.name,
            "vibe_description": h.vibe_description,
            "member_count": member_count,
            "sample_members": sample_members,
        })

    return {"nearby": nearby}


@router.get("/user/{user_id}/summary")
async def get_user_summary(
    user_id: int,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Full profile summary for a user: apartment items, vibe labels, scenario answers.
    This is the 'deep view' before visiting their apartment.
    """
    # Validate user exists
    result = await db.execute(
        select(users.c.id, users.c.name, users.c.avatar_url, users.c.bio)
        .where(users.c.id == user_id)
    )
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Vibe profile
    result = await db.execute(
        select(preference_profiles.c.weights, preference_profiles.c.vibe_labels)
        .where(preference_profiles.c.user_id == user_id)
    )
    profile = result.fetchone()
    vibe_labels = (profile.vibe_labels if profile else None) or []

    # Apartment items
    result = await db.execute(
        select(apartments.c.id).where(apartments.c.user_id == user_id)
    )
    apt = result.fetchone()
    items_by_zone: dict[str, list] = {}
    if apt:
        result = await db.execute(
            select(
                apartment_items.c.zone,
                furniture_catalog.c.name,
                furniture_catalog.c.icon_name,
            )
            .join(furniture_catalog, apartment_items.c.furniture_id == furniture_catalog.c.id)
            .where(apartment_items.c.apartment_id == apt.id)
            .order_by(apartment_items.c.zone)
        )
        for row in result.fetchall():
            zone = row.zone
            if zone not in items_by_zone:
                items_by_zone[zone] = []
            items_by_zone[zone].append({
                "name": row.name,
                "icon_name": row.icon_name,
            })

    # Active scenario responses (max 3)
    result = await db.execute(
        select(
            scenario_responses.c.selected_option,
            scenarios.c.prompt,
            scenarios.c.options,
        )
        .join(scenarios, scenario_responses.c.scenario_id == scenarios.c.id)
        .where(
            scenario_responses.c.user_id == user_id,
            scenario_responses.c.active == True,
        )
        .order_by(scenario_responses.c.answered_at.desc())
        .limit(3)
    )
    scenario_answers = []
    for row in result.fetchall():
        selected_text = None
        for opt in (row.options or []):
            if opt["id"] == row.selected_option:
                selected_text = opt["text"]
                break
        scenario_answers.append({
            "prompt": row.prompt,
            "selected_text": selected_text,
        })

    return {
        "id": user.id,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "vibe_labels": vibe_labels,
        "apartment_items": items_by_zone,
        "scenario_answers": scenario_answers,
    }


@router.post("/recalculate")
async def recalculate_neighborhoods(
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force re-clustering of all users. Debug/admin endpoint (still requires auth)."""
    await _run_clustering(db)
    result = await db.execute(select(func.count()).select_from(neighborhoods))
    count = result.scalar() or 0
    return {"detail": "Re-clustering complete", "neighborhood_count": count}
