"""
Vibe Engine — calculate preference profiles from apartment furniture choices.

Pure calculation logic, no database access. Functions accept raw data and
return computed results.
"""

# All preference dimensions (matches seed_furniture.py weights)
DIMENSIONS = [
    "tidiness", "social", "night_owl", "studious", "cooking",
    "wellness", "minimalist", "creative", "outdoorsy", "cozy",
]

# Thresholds for mapping normalized weights to human-readable labels.
# Each entry: (dimension, threshold, label)
LABEL_RULES: list[tuple[str, float, str]] = [
    ("tidiness", 0.7, "organized"),
    ("tidiness", 0.4, "easygoing about mess"),
    ("social", 0.7, "social butterfly"),
    ("social", 0.4, "likes company"),
    ("night_owl", 0.7, "night owl"),
    ("night_owl", 0.4, "stays up late sometimes"),
    ("studious", 0.7, "bookworm"),
    ("studious", 0.4, "values focus time"),
    ("cooking", 0.7, "home chef"),
    ("cooking", 0.4, "enjoys cooking"),
    ("wellness", 0.7, "wellness-focused"),
    ("wellness", 0.4, "health-conscious"),
    ("minimalist", 0.7, "minimalist"),
    ("minimalist", 0.4, "likes things simple"),
    ("creative", 0.7, "creative soul"),
    ("creative", 0.4, "appreciates art"),
    ("outdoorsy", 0.7, "nature lover"),
    ("outdoorsy", 0.4, "enjoys the outdoors"),
    ("cozy", 0.7, "comfort-first"),
    ("cozy", 0.4, "values coziness"),
]

# Conversation-starter templates for differences
CONVERSATION_STARTERS: dict[str, str] = {
    "tidiness": "You might want to discuss cleaning expectations",
    "social": "You have different social energy levels — worth chatting about guest policies",
    "night_owl": "They're a {other_label} — you might want to discuss schedules",
    "studious": "You have different study habits — worth discussing quiet hours",
    "cooking": "You differ on kitchen use — good to align on shared kitchen expectations",
    "wellness": "You have different wellness routines — consider bathroom/kitchen schedules",
    "minimalist": "You have different space preferences — discuss shared area aesthetics",
    "creative": "You have different creative energy — could be complementary!",
    "outdoorsy": "You differ on outdoor activities — great chance to try new things together",
    "cozy": "You have different comfort priorities — discuss thermostat and shared spaces",
}


def calculate_weights(items_with_weights: list[dict]) -> dict[str, float]:
    """
    Sum preference_weights from all placed items, then normalize to 0–1.

    Args:
        items_with_weights: list of dicts, each with a 'preference_weights' key
            (dict mapping dimension -> float value)

    Returns:
        dict mapping each dimension to a normalized 0–1 score
    """
    raw: dict[str, float] = {d: 0.0 for d in DIMENSIONS}

    for item in items_with_weights:
        weights = item.get("preference_weights") or {}
        for dim, val in weights.items():
            if dim in raw:
                raw[dim] += val

    # Normalize: divide by the max value across all dimensions
    max_val = max(raw.values()) if raw else 0
    if max_val == 0:
        return raw

    return {dim: round(val / max_val, 3) for dim, val in raw.items()}


def weights_to_labels(weights: dict[str, float]) -> list[str]:
    """
    Map a weight vector to human-readable vibe labels.

    Only the highest-threshold match per dimension is included.
    Returns labels sorted by their weight (strongest vibes first).
    """
    labels: list[tuple[str, float]] = []
    seen_dims: set[str] = set()

    # LABEL_RULES is sorted with higher thresholds first per dimension
    for dim, threshold, label in LABEL_RULES:
        if dim in seen_dims:
            continue
        score = weights.get(dim, 0)
        if score >= threshold:
            labels.append((label, score))
            seen_dims.add(dim)

    # Sort by weight descending so strongest vibes come first
    labels.sort(key=lambda x: x[1], reverse=True)
    return [label for label, _ in labels]


def compare_profiles(
    my_weights: dict[str, float],
    their_weights: dict[str, float],
) -> dict:
    """
    Compare two weight vectors. Returns similarities, differences,
    and conversation starters for the differences.

    Args:
        my_weights: current user's normalized weights
        their_weights: other user's normalized weights

    Returns:
        {
            "similarities": [{"dimension": str, "label": str}, ...],
            "differences": [{"dimension": str, "my_label": str, "their_label": str}, ...],
            "conversation_starters": [str, ...],
        }
    """
    similarities: list[dict] = []
    differences: list[dict] = []
    conversation_starters: list[str] = []

    for dim in DIMENSIONS:
        my_score = my_weights.get(dim, 0)
        their_score = their_weights.get(dim, 0)

        my_label = _label_for_dim(dim, my_score)
        their_label = _label_for_dim(dim, their_score)

        # Skip dimensions where neither user has a meaningful score
        if my_score < 0.3 and their_score < 0.3:
            continue

        diff = abs(my_score - their_score)

        if diff < 0.25:
            # Similar — use the higher-scoring label
            label = my_label or their_label
            if label:
                similarities.append({"dimension": dim, "label": label})
        elif my_label or their_label:
            differences.append({
                "dimension": dim,
                "my_label": my_label or "neutral",
                "their_label": their_label or "neutral",
            })
            template = CONVERSATION_STARTERS.get(dim, "")
            if template:
                starter = template.replace(
                    "{other_label}", their_label or "different"
                )
                conversation_starters.append(starter)

    return {
        "similarities": similarities,
        "differences": differences,
        "conversation_starters": conversation_starters,
    }


def _label_for_dim(dim: str, score: float) -> str | None:
    """Get the best label for a single dimension at a given score."""
    for d, threshold, label in LABEL_RULES:
        if d == dim and score >= threshold:
            return label
    return None
