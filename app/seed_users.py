"""
Seed test users with apartments, preference profiles, and scenario answers.

Creates 12 users with distinct roommate personality archetypes, each with
furniture choices that produce different vibe profiles. This gives the
clustering algorithm enough data for meaningful neighborhoods.

Run with:  python -m app.seed_users

All users have password: TestPass123
(meets frontend validation: 8+ chars, uppercase, lowercase, digit)
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from datetime import datetime, timezone
from sqlalchemy import insert, select
from app.database import engine
from app.models import (
    users,
    apartments,
    apartment_items,
    preference_profiles,
    furniture_catalog,
    scenarios,
    scenario_responses,
)
from app.security import hash_password
from app.vibe_engine import calculate_weights, weights_to_labels

PASSWORD = "TestPass123"

# Each archetype: name, email, bio, and furniture names to place
ARCHETYPES = [
    {
        "name": "Jordan",
        "email": "jordan@test.com",
        "bio": "Early riser, clean freak, loves a good spreadsheet.",
        "furniture": [
            "Twin Bed", "Study Desk", "Desk Lamp", "Under-Bed Storage",
            "Reading Nook", "Shoe Rack", "Indoor Plants",
            "Tea Station", "Meal Prep Containers", "Spice Rack",
            "Quick Shower", "Minimal Vanity", "Towel Organizer",
        ],
        "scenario_answers": {"1": "a", "2": "b", "4": "a"},
    },
    {
        "name": "Riley",
        "email": "riley@test.com",
        "bio": "Night owl creative who paints at 2am.",
        "furniture": [
            "Queen Bed", "Art Desk", "LED Strip Lights", "Poster Wall",
            "Bean Bag Pit", "Record Player", "Gallery Wall",
            "Espresso Machine", "Baking Kit", "Chalkboard Menu",
            "Spa Shower", "Skincare Station", "Candles & Diffuser",
        ],
        "scenario_answers": {"1": "c", "6": "d", "7": "a"},
    },
    {
        "name": "Casey",
        "email": "casey@test.com",
        "bio": "Social butterfly, always hosting game night.",
        "furniture": [
            "Queen Bed", "Fairy Lights", "Bookshelf",
            "Big Couch", "Board Game Shelf", "Gallery Wall",
            "Cast Iron Set", "Baking Kit", "Spice Rack",
            "Spa Shower", "Skincare Station", "Bathroom Plants",
        ],
        "scenario_answers": {"9": "c", "11": "c", "12": "d"},
    },
    {
        "name": "Morgan",
        "email": "morgan@test.com",
        "bio": "Wellness nerd. Yoga at dawn, smoothie by 7.",
        "furniture": [
            "Queen Bed", "Plant Collection", "Fairy Lights",
            "Reading Nook", "Indoor Plants", "Yoga Mat Corner",
            "Smoothie Blender", "Meal Prep Containers", "Herb Garden",
            "Spa Shower", "Skincare Station", "Candles & Diffuser", "Bathroom Plants",
        ],
        "scenario_answers": {"13": "a", "15": "a", "16": "a"},
    },
    {
        "name": "Taylor",
        "email": "taylor@test.com",
        "bio": "Minimalist to the core. If I don't need it, I don't own it.",
        "furniture": [
            "Twin Bed", "Study Desk", "Desk Lamp",
            "Reading Nook", "Shoe Rack",
            "Tea Station", "Microwave & Ramen",
            "Quick Shower", "Minimal Vanity", "Towel Organizer",
        ],
        "scenario_answers": {"4": "a", "17": "b", "23": "c"},
    },
    {
        "name": "Alex",
        "email": "alex@test.com",
        "bio": "Bookworm and aspiring novelist. Libraries are my happy place.",
        "furniture": [
            "Loft Bed", "Study Desk", "Desk Lamp", "Bookshelf",
            "Reading Nook", "Indoor Plants",
            "Tea Station", "Meal Prep Containers",
            "Quick Shower", "Minimal Vanity", "Magazine Rack",
        ],
        "scenario_answers": {"5": "c", "8": "a", "14": "b"},
    },
    {
        "name": "Sam",
        "email": "sam@test.com",
        "bio": "Home chef. My cast iron is seasoned better than your life.",
        "furniture": [
            "Queen Bed", "Fairy Lights", "Plant Collection",
            "Big Couch", "TV Setup", "Indoor Plants",
            "Espresso Machine", "Cast Iron Set", "Spice Rack", "Herb Garden",
            "Spa Shower", "Skincare Station", "Candles & Diffuser",
        ],
        "scenario_answers": {"15": "a", "16": "a", "3": "c"},
    },
    {
        "name": "Jamie",
        "email": "jamie@test.com",
        "bio": "Outdoorsy and active. My room smells like campfire.",
        "furniture": [
            "Twin Bed", "Plant Collection",
            "Bean Bag Pit", "Indoor Plants", "Yoga Mat Corner",
            "Smoothie Blender", "Herb Garden",
            "Quick Shower", "Bathroom Plants",
        ],
        "scenario_answers": {"13": "a", "14": "a", "19": "d"},
    },
    {
        "name": "Avery",
        "email": "avery@test.com",
        "bio": "Cozy homebody. Blankets are a lifestyle.",
        "furniture": [
            "Queen Bed", "Fairy Lights", "Bookshelf", "Plant Collection",
            "Reading Nook", "Record Player", "Indoor Plants",
            "Tea Station", "Baking Kit", "Chalkboard Menu",
            "Spa Shower", "Skincare Station", "Candles & Diffuser", "Bathroom Plants",
        ],
        "scenario_answers": {"6": "a", "8": "b", "21": "b"},
    },
    {
        "name": "Quinn",
        "email": "quinn@test.com",
        "bio": "Party in the front, organized in the back.",
        "furniture": [
            "Queen Bed", "LED Strip Lights", "Poster Wall",
            "Big Couch", "TV Setup", "Board Game Shelf",
            "Espresso Machine", "Cast Iron Set",
            "Quick Shower", "Minimal Vanity",
        ],
        "scenario_answers": {"9": "c", "10": "d", "12": "c"},
    },
    {
        "name": "Drew",
        "email": "drew@test.com",
        "bio": "Gym rat meets neat freak. Protein shaker always clean.",
        "furniture": [
            "Twin Bed", "Study Desk", "Desk Lamp", "Under-Bed Storage",
            "Yoga Mat Corner", "Shoe Rack",
            "Smoothie Blender", "Meal Prep Containers",
            "Quick Shower", "Minimal Vanity", "Towel Organizer",
        ],
        "scenario_answers": {"1": "a", "2": "a", "4": "a"},
    },
    {
        "name": "Sage",
        "email": "sage@test.com",
        "bio": "Art student. Creative chaos is my aesthetic.",
        "furniture": [
            "Loft Bed", "Art Desk", "LED Strip Lights", "Poster Wall",
            "Bean Bag Pit", "Record Player", "Gallery Wall",
            "Espresso Machine", "Chalkboard Menu",
            "Spa Shower", "Skincare Station", "Candles & Diffuser",
        ],
        "scenario_answers": {"5": "d", "7": "a", "8": "c"},
    },
]


async def seed():
    hashed = hash_password(PASSWORD)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with engine.begin() as conn:
        # Build furniture name→row lookup
        result = await conn.execute(select(furniture_catalog))
        furniture_rows = result.fetchall()
        name_to_furniture = {row.name: row for row in furniture_rows}

        if not name_to_furniture:
            print("ERROR: Furniture catalog is empty. Run `python -m app.seed_furniture` first.")
            return

        # Get scenario IDs (ordered by id so we can reference by position)
        result = await conn.execute(
            select(scenarios.c.id).order_by(scenarios.c.id)
        )
        scenario_ids = [row.id for row in result.fetchall()]

        if not scenario_ids:
            print("WARNING: No scenarios found. Run `python -m app.seed_scenarios` first for scenario answers.")

        created = 0
        for arch in ARCHETYPES:
            # Check if user already exists
            result = await conn.execute(
                select(users.c.id).where(users.c.email == arch["email"])
            )
            existing = result.fetchone()
            if existing:
                print(f"  Skipping {arch['name']} — already exists")
                continue

            # Create user
            result = await conn.execute(
                insert(users).values(
                    email=arch["email"],
                    password=hashed,
                    name=arch["name"],
                    bio=arch["bio"],
                ).returning(users.c.id)
            )
            user_id = result.scalar_one()

            # Create apartment
            result = await conn.execute(
                insert(apartments).values(
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                ).returning(apartments.c.id)
            )
            apt_id = result.scalar_one()

            # Place furniture items
            items_with_weights = []
            for fname in arch["furniture"]:
                furn = name_to_furniture.get(fname)
                if not furn:
                    print(f"  Warning: furniture '{fname}' not found in catalog")
                    continue
                await conn.execute(
                    insert(apartment_items).values(
                        apartment_id=apt_id,
                        furniture_id=furn.id,
                        zone=furn.zone,
                        position_x=0,
                        position_y=0,
                    )
                )
                items_with_weights.append(
                    {"preference_weights": furn.preference_weights}
                )

            # Calculate and store preference profile
            weights = calculate_weights(items_with_weights)
            labels = weights_to_labels(weights)
            await conn.execute(
                insert(preference_profiles).values(
                    user_id=user_id,
                    weights=weights,
                    vibe_labels=labels,
                    updated_at=now,
                )
            )

            # Add scenario responses
            answers_added = 0
            for pos_str, option_id in arch["scenario_answers"].items():
                pos = int(pos_str) - 1  # 1-indexed in archetype data
                if pos < len(scenario_ids):
                    sid = scenario_ids[pos]
                    await conn.execute(
                        insert(scenario_responses).values(
                            user_id=user_id,
                            scenario_id=sid,
                            selected_option=option_id,
                            answered_at=now,
                            active=True,
                        )
                    )
                    answers_added += 1

            created += 1
            print(f"  Created {arch['name']} ({arch['email']}) — {len(items_with_weights)} items, {answers_added} scenarios, labels: {labels}")

    print(f"\nSeeded {created} test users. Password for all: {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
