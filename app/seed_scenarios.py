"""
Seed the scenarios table with daily situational questions.

Run with:  python -m app.seed_scenarios
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import insert, delete
from app.database import engine
from app.models import scenarios

SCENARIOS: list[dict] = [
    # ─── CLEANLINESS ─────────────────────────────────────────────
    {
        "prompt": "It's Sunday morning. Your roommate had people over last night. The kitchen is wrecked. They're still asleep. What do you do?",
        "options": [
            {"id": "a", "text": "Clean it up — I can't relax in a mess"},
            {"id": "b", "text": "Leave it and text them to handle it when they wake up"},
            {"id": "c", "text": "It doesn't really bother me — I'll deal with my own stuff"},
            {"id": "d", "text": "Clean my part and leave the rest for them"},
        ],
    },
    {
        "prompt": "The bathroom sink has been getting grimier every day. Neither of you has cleaned it. What's your move?",
        "options": [
            {"id": "a", "text": "Just clean it — someone has to"},
            {"id": "b", "text": "Suggest a cleaning schedule so this doesn't keep happening"},
            {"id": "c", "text": "Mention it casually and hope they take the hint"},
            {"id": "d", "text": "Honestly, I haven't noticed until now"},
        ],
    },
    {
        "prompt": "Your roommate leaves dishes in the sink 'to soak' but they've been there two days. What do you do?",
        "options": [
            {"id": "a", "text": "Wash them — it's faster than having a conversation about it"},
            {"id": "b", "text": "Stack them neatly on their side of the counter"},
            {"id": "c", "text": "Ask them directly to clean up"},
            {"id": "d", "text": "Two days? That's nothing — I've done worse"},
        ],
    },
    {
        "prompt": "How do you feel about shoes in the apartment?",
        "options": [
            {"id": "a", "text": "Shoes off at the door, always"},
            {"id": "b", "text": "I prefer shoes off but won't enforce it"},
            {"id": "c", "text": "I don't really care either way"},
            {"id": "d", "text": "I usually keep my shoes on inside"},
        ],
    },

    # ─── NOISE ───────────────────────────────────────────────────
    {
        "prompt": "You're studying for finals. Your roommate starts a video call in the shared space. What's your move?",
        "options": [
            {"id": "a", "text": "Put on headphones and power through"},
            {"id": "b", "text": "Politely ask them to move to their room"},
            {"id": "c", "text": "Go study somewhere else — library, coffee shop"},
            {"id": "d", "text": "Join the call — studying can wait"},
        ],
    },
    {
        "prompt": "It's 11 PM on a Tuesday. You want to watch a show on the living room TV. Your roommate has an early class. What do you do?",
        "options": [
            {"id": "a", "text": "Watch on my phone with headphones instead"},
            {"id": "b", "text": "Watch on the TV but keep the volume low"},
            {"id": "c", "text": "Ask if they mind — if their door's closed they probably can't hear"},
            {"id": "d", "text": "It's the living room — I shouldn't have to tiptoe"},
        ],
    },
    {
        "prompt": "Your roommate plays music without headphones while cooking. How do you feel?",
        "options": [
            {"id": "a", "text": "Love it — makes the apartment feel alive"},
            {"id": "b", "text": "Fine as long as it's at a reasonable volume"},
            {"id": "c", "text": "I'd prefer they use headphones"},
            {"id": "d", "text": "Depends entirely on the music"},
        ],
    },
    {
        "prompt": "What's your ideal apartment sound level on a weeknight?",
        "options": [
            {"id": "a", "text": "Library quiet — I need silence to recharge"},
            {"id": "b", "text": "Background noise is fine — music, TV on low"},
            {"id": "c", "text": "I like some energy — conversations, music playing"},
            {"id": "d", "text": "The louder the better — silence makes me anxious"},
        ],
    },

    # ─── GUESTS ──────────────────────────────────────────────────
    {
        "prompt": "Your roommate asks if their friend can crash at your place for a week.",
        "options": [
            {"id": "a", "text": "A week is a lot — I'd say no or suggest a shorter stay"},
            {"id": "b", "text": "Sure, as long as they're respectful of shared spaces"},
            {"id": "c", "text": "Fine by me — the more the merrier"},
            {"id": "d", "text": "Okay but we should split any extra costs"},
        ],
    },
    {
        "prompt": "Your roommate's significant other is over 4-5 nights a week. How do you feel?",
        "options": [
            {"id": "a", "text": "That's basically a third roommate — we need to talk about it"},
            {"id": "b", "text": "It's fine as long as they're not in my way"},
            {"id": "c", "text": "I'd want them to chip in for utilities"},
            {"id": "d", "text": "No problem — I like having people around"},
        ],
    },
    {
        "prompt": "You come home to find your roommate hosting a small get-together you didn't know about. Your reaction?",
        "options": [
            {"id": "a", "text": "I wish they'd told me, but I'll join in"},
            {"id": "b", "text": "I'd be annoyed — a heads up would be nice"},
            {"id": "c", "text": "Cool, I love spontaneous hangs"},
            {"id": "d", "text": "I'd retreat to my room — I need my space"},
        ],
    },
    {
        "prompt": "How much notice do you need before your roommate has people over?",
        "options": [
            {"id": "a", "text": "At least a day — I like to mentally prepare"},
            {"id": "b", "text": "A few hours is plenty"},
            {"id": "c", "text": "A quick text right before is fine"},
            {"id": "d", "text": "No notice needed — it's their home too"},
        ],
    },

    # ─── SCHEDULES ───────────────────────────────────────────────
    {
        "prompt": "Your roommate's alarm goes off at 6am every day. You don't have class until noon.",
        "options": [
            {"id": "a", "text": "Ask them to use a vibrating alarm or keep it quieter"},
            {"id": "b", "text": "Get earplugs — it's their right to wake up early"},
            {"id": "c", "text": "Honestly, I'd probably sleep through it"},
            {"id": "d", "text": "Maybe I should start waking up earlier too"},
        ],
    },
    {
        "prompt": "It's Saturday morning. What time are you up?",
        "options": [
            {"id": "a", "text": "Before 8am — I don't waste weekends sleeping in"},
            {"id": "b", "text": "Around 9-10am — a little later than weekdays"},
            {"id": "c", "text": "Noon-ish — Saturdays are for sleeping in"},
            {"id": "d", "text": "What is morning? I went to bed at 4am"},
        ],
    },
    {
        "prompt": "Your roommate wants to coordinate grocery shopping to save trips. Thoughts?",
        "options": [
            {"id": "a", "text": "Great idea — let's make a shared list"},
            {"id": "b", "text": "I'd rather shop on my own schedule"},
            {"id": "c", "text": "Sure, but I'm not committing to a regular schedule"},
            {"id": "d", "text": "I mostly eat out anyway"},
        ],
    },
    {
        "prompt": "How do you feel about shared meals with your roommate?",
        "options": [
            {"id": "a", "text": "I'd love to cook together regularly"},
            {"id": "b", "text": "Occasionally would be nice — once a week maybe"},
            {"id": "c", "text": "I prefer to eat on my own schedule"},
            {"id": "d", "text": "I'm down for ordering food together"},
        ],
    },

    # ─── CONFLICT ────────────────────────────────────────────────
    {
        "prompt": "You notice your roommate has been using your groceries without asking.",
        "options": [
            {"id": "a", "text": "Bring it up directly but calmly"},
            {"id": "b", "text": "Label my stuff and hope they get the message"},
            {"id": "c", "text": "It's not a big deal — I'd share anyway"},
            {"id": "d", "text": "Start a shared grocery fund so it's not an issue"},
        ],
    },
    {
        "prompt": "Your roommate borrowed something of yours and returned it damaged. What do you do?",
        "options": [
            {"id": "a", "text": "Tell them directly and ask them to replace it"},
            {"id": "b", "text": "Mention it but say it's no big deal"},
            {"id": "c", "text": "Let it go — stuff happens"},
            {"id": "d", "text": "Stop lending things and quietly set that boundary"},
        ],
    },
    {
        "prompt": "You and your roommate disagree on the thermostat temperature. How do you resolve it?",
        "options": [
            {"id": "a", "text": "Compromise on a middle temperature"},
            {"id": "b", "text": "Whoever's more uncomfortable gets priority"},
            {"id": "c", "text": "Alternate days — fair is fair"},
            {"id": "d", "text": "Layer up or strip down — I don't want to argue about it"},
        ],
    },
    {
        "prompt": "Something your roommate does is mildly annoying but not a big deal. Do you bring it up?",
        "options": [
            {"id": "a", "text": "Yes — small things build up if you don't address them"},
            {"id": "b", "text": "Only if it happens repeatedly"},
            {"id": "c", "text": "No — I'd rather keep the peace"},
            {"id": "d", "text": "I'd joke about it and see if they pick up on it"},
        ],
    },
    {
        "prompt": "Your roommate is going through a tough time and has been leaving messes, being short with you. What's your approach?",
        "options": [
            {"id": "a", "text": "Give them space and pick up the slack for a bit"},
            {"id": "b", "text": "Check in on them but still set boundaries about shared spaces"},
            {"id": "c", "text": "Leave them alone — they'll come to me if they need to"},
            {"id": "d", "text": "Suggest we do something fun together to take their mind off it"},
        ],
    },

    # ─── SPACE & BOUNDARIES ──────────────────────────────────────
    {
        "prompt": "Your roommate walks into your room without knocking. How do you react?",
        "options": [
            {"id": "a", "text": "Ask them to please knock next time"},
            {"id": "b", "text": "It depends on what I'm doing — usually I don't mind"},
            {"id": "c", "text": "No big deal — we're roommates"},
            {"id": "d", "text": "I always keep my door open anyway"},
        ],
    },
    {
        "prompt": "How do you feel about sharing food, toiletries, and household items?",
        "options": [
            {"id": "a", "text": "What's mine is yours — sharing is caring"},
            {"id": "b", "text": "Some shared staples are fine, but I like my own stuff too"},
            {"id": "c", "text": "I prefer to keep things separate unless we agree upfront"},
            {"id": "d", "text": "Strictly separate everything"},
        ],
    },
]


async def seed(eng=engine):
    async with eng.begin() as conn:
        # Clear existing scenarios (idempotent)
        await conn.execute(delete(scenarios))

        for item in SCENARIOS:
            await conn.execute(
                insert(scenarios).values(
                    prompt=item["prompt"],
                    options=item["options"],
                    active=True,
                )
            )

    print(f"Seeded {len(SCENARIOS)} scenarios.")


if __name__ == "__main__":
    asyncio.run(seed())
