"""
Seed the quick_pick_questions table with trade-off questions.

These are rapid-fire either/or dilemmas for the Quick Picks feature.
Both users answer the same 5 questions independently, then see
side-by-side results showing where they agree and diverge.

Run with:  python -m app.seed_quickpicks
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import insert, delete
from app.database import engine
from app.models import quick_pick_questions

QUESTIONS: list[dict] = [
    # ─── CLEANLINESS ─────────────────────────────────────────────
    {
        "prompt": "Dishes pile up. When's the cutoff?",
        "option_a": "Same day",
        "option_b": "By tomorrow morning",
        "category": "cleanliness",
    },
    {
        "prompt": "The trash is full. Whose job is it?",
        "option_a": "Whoever fills it takes it out",
        "option_b": "Take turns on a schedule",
        "category": "cleanliness",
    },
    {
        "prompt": "Cleaning the bathroom — how often?",
        "option_a": "Weekly, no exceptions",
        "option_b": "When it looks like it needs it",
        "category": "cleanliness",
    },
    {
        "prompt": "Shoes in the apartment?",
        "option_a": "Off at the door, always",
        "option_b": "Wear them wherever, it's fine",
        "category": "cleanliness",
    },

    # ─── NOISE ───────────────────────────────────────────────────
    {
        "prompt": "It's 11pm on a Tuesday. Music?",
        "option_a": "Headphones only",
        "option_b": "Low volume is fine",
        "category": "noise",
    },
    {
        "prompt": "Morning alarm goes off. How many snoozes?",
        "option_a": "Zero — up on the first one",
        "option_b": "At least three, I need the warm-up",
        "category": "noise",
    },
    {
        "prompt": "Video calls in shared spaces?",
        "option_a": "Always take them in your room",
        "option_b": "Shared space is fine if it's quick",
        "category": "noise",
    },
    {
        "prompt": "Weekend mornings — noise level?",
        "option_a": "Keep it quiet until noon",
        "option_b": "Normal volume, it's not a weeknight",
        "category": "noise",
    },

    # ─── GUESTS ──────────────────────────────────────────────────
    {
        "prompt": "Guest wants to crash for a week.",
        "option_a": "Always fine if they ask",
        "option_b": "3 days max, hard rule",
        "category": "guests",
    },
    {
        "prompt": "Surprise get-together at your place tonight?",
        "option_a": "Love it — spontaneous is the best",
        "option_b": "Need at least a day's notice",
        "category": "guests",
    },
    {
        "prompt": "Partner staying over — how many nights a week is OK?",
        "option_a": "As many as they want",
        "option_b": "Cap it at 3 nights",
        "category": "guests",
    },
    {
        "prompt": "Friend shows up unannounced. Your reaction?",
        "option_a": "The more the merrier!",
        "option_b": "They should've texted first",
        "category": "guests",
    },

    # ─── SPACE ───────────────────────────────────────────────────
    {
        "prompt": "One big bedroom, one small. How to decide?",
        "option_a": "Whoever pays more gets it",
        "option_b": "First come first served",
        "category": "space",
    },
    {
        "prompt": "Sharing groceries or keeping them separate?",
        "option_a": "Shared fund, cook together",
        "option_b": "Separate shelves, separate food",
        "category": "space",
    },
    {
        "prompt": "Living room TV — who picks what to watch?",
        "option_a": "Whoever's there first",
        "option_b": "Alternate nights",
        "category": "space",
    },

    # ─── SCHEDULES ───────────────────────────────────────────────
    {
        "prompt": "Shared bathroom morning routine?",
        "option_a": "Set a schedule",
        "option_b": "Wing it, we'll figure it out",
        "category": "schedules",
    },
    {
        "prompt": "Rent is due. How do you split it?",
        "option_a": "Exactly 50/50, always",
        "option_b": "Adjust based on room size and amenities",
        "category": "schedules",
    },
    {
        "prompt": "Thermostat wars. How to settle it?",
        "option_a": "Set it and forget it — agree on one temp",
        "option_b": "Whoever's home gets to adjust it",
        "category": "schedules",
    },
]


async def seed():
    async with engine.begin() as conn:
        # Clear existing questions (idempotent)
        await conn.execute(delete(quick_pick_questions))

        for q in QUESTIONS:
            await conn.execute(
                insert(quick_pick_questions).values(
                    prompt=q["prompt"],
                    option_a=q["option_a"],
                    option_b=q["option_b"],
                    category=q["category"],
                )
            )

    print(f"Seeded {len(QUESTIONS)} quick pick questions.")


if __name__ == "__main__":
    asyncio.run(seed())
