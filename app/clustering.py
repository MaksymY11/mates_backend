"""
Lightweight distance-based clustering for neighborhoods.

Pure Python — no numpy dependency. Groups users by preference profile
similarity using k-means, auto-generates neighborhood names and
vibe descriptions from centroid dominant traits.
"""

import math
import random
from app.vibe_engine import DIMENSIONS

# Number of clusters to target (adjusted down if fewer users)
DEFAULT_K = 6
MAX_ITERATIONS = 20

# Mapping from dominant dimension pairs to neighborhood names + descriptions
NEIGHBORHOOD_THEMES: dict[tuple[str, str], tuple[str, str]] = {
    ("tidiness", "studious"): (
        "Sunrise Terrace",
        "Early risers who keep things tidy and love a quiet morning",
    ),
    ("tidiness", "minimalist"): (
        "Crystal Commons",
        "Clean-cut minimalists who believe less is more",
    ),
    ("social", "night_owl"): (
        "Night Owl Nook",
        "Social night owls who come alive after dark",
    ),
    ("social", "cooking"): (
        "Kitchen Table Circle",
        "Social cooks who bond over shared meals",
    ),
    ("night_owl", "creative"): (
        "Midnight Studio",
        "Creative night owls burning the midnight oil",
    ),
    ("studious", "minimalist"): (
        "Scholar's Row",
        "Focused minds who prefer a distraction-free space",
    ),
    ("cooking", "cozy"): (
        "Hearth & Home",
        "Comfort-first cooks who make any place feel like home",
    ),
    ("wellness", "outdoorsy"): (
        "Trailside Lodge",
        "Nature lovers with a wellness mindset",
    ),
    ("creative", "cozy"): (
        "Cozy Canvas",
        "Creative souls who need a comfortable nest to create in",
    ),
    ("outdoorsy", "social"): (
        "Basecamp Commons",
        "Adventurous extroverts always planning the next outing",
    ),
    ("wellness", "tidiness"): (
        "Zen Garden",
        "Health-conscious organizers who value calm, tidy spaces",
    ),
    ("cozy", "night_owl"): (
        "Blanket Fort Lane",
        "Cozy night owls who love a good late-night wind-down",
    ),
}

# Fallback names when no theme matches
FALLBACK_NAMES = [
    ("The Commons", "A friendly mix of roommate styles"),
    ("Maple Court", "A welcoming blend of different vibes"),
    ("Ivy Lane", "A diverse group with something in common"),
    ("Cedar Circle", "An eclectic community finding their groove"),
    ("Willow Way", "A balanced neighborhood of varied tastes"),
    ("Pine Ridge", "A down-to-earth crew with shared values"),
    ("Birch Hall", "A community that brings out the best in each other"),
    ("Oak Terrace", "A grounded group with room for everyone"),
]

NEW_ARRIVALS_NAME = "New Arrivals"
NEW_ARRIVALS_DESC = "Fresh faces still setting up their apartments — welcome!"


def euclidean_distance(a: dict[str, float], b: dict[str, float]) -> float:
    total = 0.0
    for dim in DIMENSIONS:
        diff = a.get(dim, 0.0) - b.get(dim, 0.0)
        total += diff * diff
    return math.sqrt(total)


def similarity_score(a: dict[str, float], b: dict[str, float]) -> float:
    """Normalized Euclidean similarity: 1.0 = identical, 0.0 = maximally different."""
    max_dist = math.sqrt(len(DIMENSIONS))  # worst case: all dims differ by 1.0
    dist = euclidean_distance(a, b)
    return 1.0 - (dist / max_dist)


def _compute_centroid(profiles: list[dict[str, float]]) -> dict[str, float]:
    if not profiles:
        return {d: 0.0 for d in DIMENSIONS}
    n = len(profiles)
    centroid = {d: 0.0 for d in DIMENSIONS}
    for p in profiles:
        for d in DIMENSIONS:
            centroid[d] += p.get(d, 0.0)
    return {d: round(v / n, 4) for d, v in centroid.items()}


def _name_from_centroid(centroid: dict[str, float], used_names: set[str]) -> tuple[str, str]:
    """Generate a neighborhood name + description from the centroid's top traits."""
    sorted_dims = sorted(DIMENSIONS, key=lambda d: centroid.get(d, 0), reverse=True)
    top_two = (sorted_dims[0], sorted_dims[1])

    # Try both orderings
    for pair in [top_two, (top_two[1], top_two[0])]:
        if pair in NEIGHBORHOOD_THEMES:
            name, desc = NEIGHBORHOOD_THEMES[pair]
            if name not in used_names:
                return name, desc

    # Fallback
    for name, desc in FALLBACK_NAMES:
        if name not in used_names:
            return name, desc

    return f"Neighborhood {len(used_names) + 1}", "A unique community of roommates"


def kmeans_cluster(
    user_profiles: list[tuple[int, dict[str, float]]],
    k: int = DEFAULT_K,
) -> list[dict]:
    """
    Run k-means clustering on user preference profiles.

    Args:
        user_profiles: list of (user_id, weights_dict) tuples
        k: number of clusters

    Returns:
        list of cluster dicts:
        {
            "centroid": {dim: float},
            "name": str,
            "vibe_description": str,
            "members": [(user_id, similarity_score), ...]
        }
    """
    if not user_profiles:
        return []

    k = min(k, len(user_profiles))
    if k <= 0:
        return []

    # Initialize centroids by picking k random profiles
    indices = random.sample(range(len(user_profiles)), k)
    centroids = [dict(user_profiles[i][1]) for i in indices]

    assignments: list[int] = [0] * len(user_profiles)

    for _ in range(MAX_ITERATIONS):
        changed = False

        # Assign each user to nearest centroid
        for idx, (uid, weights) in enumerate(user_profiles):
            best_cluster = 0
            best_dist = float("inf")
            for c_idx, centroid in enumerate(centroids):
                dist = euclidean_distance(weights, centroid)
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = c_idx
            if assignments[idx] != best_cluster:
                changed = True
                assignments[idx] = best_cluster

        if not changed:
            break

        # Recompute centroids
        for c_idx in range(k):
            cluster_profiles = [
                user_profiles[i][1]
                for i in range(len(user_profiles))
                if assignments[i] == c_idx
            ]
            if cluster_profiles:
                centroids[c_idx] = _compute_centroid(cluster_profiles)

    # Build result
    used_names: set[str] = set()
    clusters: list[dict] = []

    for c_idx in range(k):
        centroid = centroids[c_idx]
        members_indices = [i for i in range(len(user_profiles)) if assignments[i] == c_idx]

        if not members_indices:
            continue

        name, desc = _name_from_centroid(centroid, used_names)
        used_names.add(name)

        members = []
        for i in members_indices:
            uid, weights = user_profiles[i]
            sim = similarity_score(weights, centroid)
            members.append((uid, round(sim, 3)))

        clusters.append({
            "centroid": centroid,
            "name": name,
            "vibe_description": desc,
            "members": members,
        })

    return clusters
