"""
Seed the furniture_catalog and room_style_presets tables.

Run with:  python -m app.seed_furniture

TODO: Frontend (Session 2) needs a Map<String, IconData> to resolve each
      icon_name to a Flutter Icons constant. Names here are descriptive
      (e.g. "queen_bed", "fairy_lights") and may not match a Material Icon
      exactly — the frontend mapping decides the visual fallback.
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import insert, delete, select
from app.database import engine
from app.models import furniture_catalog, room_style_presets

# ── Furniture Data ───────────────────────────────────────────────
# preference_weights dimensions:
#   tidiness, social, night_owl, studious, cooking, wellness,
#   minimalist, creative, outdoorsy, cozy

FURNITURE: list[dict] = [
    # ─── BEDROOM ─────────────────────────────────────────────
    # Beds (constraint_group: bedroom_bed — pick one)
    {"zone": "bedroom", "category": "bed", "name": "Twin Bed",
     "description": "Simple and space-saving",
     "icon_name": "twin_bed", "constraint_group": "bedroom_bed",
     "preference_weights": {"minimalist": 0.7, "studious": 0.3}},
    {"zone": "bedroom", "category": "bed", "name": "Queen Bed",
     "description": "Roomy and comfortable",
     "icon_name": "queen_bed", "constraint_group": "bedroom_bed",
     "preference_weights": {"cozy": 0.8, "wellness": 0.3}},
    {"zone": "bedroom", "category": "bed", "name": "Loft Bed",
     "description": "Desk underneath, bed on top",
     "icon_name": "loft_bed", "constraint_group": "bedroom_bed",
     "preference_weights": {"studious": 0.7, "creative": 0.4, "minimalist": 0.3}},
    # Desk area
    {"zone": "bedroom", "category": "desk", "name": "Study Desk",
     "description": "Clean workspace for getting things done",
     "icon_name": "study_desk", "constraint_group": None,
     "preference_weights": {"studious": 0.8, "tidiness": 0.4}},
    {"zone": "bedroom", "category": "desk", "name": "Art Desk",
     "description": "Wide surface with supply organizers",
     "icon_name": "art_desk", "constraint_group": None,
     "preference_weights": {"creative": 0.9, "studious": 0.3}},
    # Lighting (constraint_group: bedroom_lighting)
    {"zone": "bedroom", "category": "lighting", "name": "Desk Lamp",
     "description": "Focused task lighting",
     "icon_name": "desk_lamp", "constraint_group": "bedroom_lighting",
     "preference_weights": {"studious": 0.6, "night_owl": 0.4}},
    {"zone": "bedroom", "category": "lighting", "name": "Fairy Lights",
     "description": "Warm string lights for ambiance",
     "icon_name": "fairy_lights", "constraint_group": "bedroom_lighting",
     "preference_weights": {"cozy": 0.8, "creative": 0.3}},
    {"zone": "bedroom", "category": "lighting", "name": "LED Strip Lights",
     "description": "Color-changing mood lighting",
     "icon_name": "led_strip", "constraint_group": "bedroom_lighting",
     "preference_weights": {"night_owl": 0.7, "social": 0.3, "creative": 0.3}},
    # Extras
    {"zone": "bedroom", "category": "decor", "name": "Bookshelf",
     "description": "Tall shelf for books and trinkets",
     "icon_name": "bookshelf", "constraint_group": None,
     "preference_weights": {"studious": 0.6, "tidiness": 0.4}},
    {"zone": "bedroom", "category": "decor", "name": "Plant Collection",
     "description": "A cluster of potted plants",
     "icon_name": "potted_plants", "constraint_group": None,
     "preference_weights": {"wellness": 0.6, "cozy": 0.4, "outdoorsy": 0.3}},
    {"zone": "bedroom", "category": "decor", "name": "Poster Wall",
     "description": "Covered in posters and prints",
     "icon_name": "poster_wall", "constraint_group": None,
     "preference_weights": {"creative": 0.7, "social": 0.2}},
    {"zone": "bedroom", "category": "storage", "name": "Under-Bed Storage",
     "description": "Bins neatly tucked away",
     "icon_name": "under_bed_storage", "constraint_group": None,
     "preference_weights": {"tidiness": 0.8, "minimalist": 0.5}},

    # ─── LIVING ROOM ─────────────────────────────────────────
    # Seating (constraint_group: living_seating)
    {"zone": "living_room", "category": "seating", "name": "Big Couch",
     "description": "Seats the whole crew",
     "icon_name": "couch", "constraint_group": "living_seating",
     "preference_weights": {"social": 0.9, "cozy": 0.5}},
    {"zone": "living_room", "category": "seating", "name": "Bean Bag Pit",
     "description": "Casual floor seating",
     "icon_name": "bean_bag", "constraint_group": "living_seating",
     "preference_weights": {"social": 0.7, "creative": 0.4, "cozy": 0.3}},
    {"zone": "living_room", "category": "seating", "name": "Reading Nook",
     "description": "A comfy corner chair with a lamp",
     "icon_name": "reading_nook", "constraint_group": "living_seating",
     "preference_weights": {"studious": 0.6, "cozy": 0.7, "minimalist": 0.3}},
    # Entertainment (constraint_group: living_entertainment)
    {"zone": "living_room", "category": "entertainment", "name": "TV Setup",
     "description": "Big screen with streaming",
     "icon_name": "tv", "constraint_group": "living_entertainment",
     "preference_weights": {"social": 0.5, "night_owl": 0.4, "cozy": 0.3}},
    {"zone": "living_room", "category": "entertainment", "name": "Board Game Shelf",
     "description": "Stacked with classics and party games",
     "icon_name": "board_games", "constraint_group": "living_entertainment",
     "preference_weights": {"social": 0.9, "creative": 0.3}},
    {"zone": "living_room", "category": "entertainment", "name": "Record Player",
     "description": "Vinyl collection and warm sound",
     "icon_name": "record_player", "constraint_group": "living_entertainment",
     "preference_weights": {"creative": 0.7, "cozy": 0.5}},
    # Extras
    {"zone": "living_room", "category": "decor", "name": "Gallery Wall",
     "description": "Photos, art, and memories",
     "icon_name": "gallery_wall", "constraint_group": None,
     "preference_weights": {"creative": 0.7, "social": 0.4}},
    {"zone": "living_room", "category": "decor", "name": "Indoor Plants",
     "description": "Big leafy statement plants",
     "icon_name": "indoor_plants", "constraint_group": None,
     "preference_weights": {"wellness": 0.6, "tidiness": 0.3, "cozy": 0.3}},
    {"zone": "living_room", "category": "decor", "name": "Shoe Rack",
     "description": "Organized entryway storage",
     "icon_name": "shoe_rack", "constraint_group": None,
     "preference_weights": {"tidiness": 0.9, "minimalist": 0.4}},
    {"zone": "living_room", "category": "exercise", "name": "Yoga Mat Corner",
     "description": "Space for stretching and workouts",
     "icon_name": "yoga_mat", "constraint_group": None,
     "preference_weights": {"wellness": 0.9, "outdoorsy": 0.3}},

    # ─── KITCHEN ─────────────────────────────────────────────
    # Appliances (constraint_group: kitchen_beverage)
    {"zone": "kitchen", "category": "appliance", "name": "Espresso Machine",
     "description": "Serious coffee setup",
     "icon_name": "espresso_machine", "constraint_group": "kitchen_beverage",
     "preference_weights": {"studious": 0.4, "night_owl": 0.5, "cooking": 0.3}},
    {"zone": "kitchen", "category": "appliance", "name": "Tea Station",
     "description": "Kettle and a wall of teas",
     "icon_name": "tea_station", "constraint_group": "kitchen_beverage",
     "preference_weights": {"cozy": 0.6, "wellness": 0.5, "minimalist": 0.2}},
    {"zone": "kitchen", "category": "appliance", "name": "Smoothie Blender",
     "description": "High-powered blender for health drinks",
     "icon_name": "blender", "constraint_group": "kitchen_beverage",
     "preference_weights": {"wellness": 0.8, "outdoorsy": 0.3}},
    # Cookware
    {"zone": "kitchen", "category": "cookware", "name": "Cast Iron Set",
     "description": "Heavy-duty pans for real cooking",
     "icon_name": "cast_iron_pan", "constraint_group": None,
     "preference_weights": {"cooking": 0.9, "social": 0.3}},
    {"zone": "kitchen", "category": "cookware", "name": "Baking Kit",
     "description": "Mixing bowls, sheet pans, the works",
     "icon_name": "baking_kit", "constraint_group": None,
     "preference_weights": {"cooking": 0.7, "creative": 0.5, "social": 0.4}},
    {"zone": "kitchen", "category": "cookware", "name": "Microwave & Ramen",
     "description": "Quick meals, zero fuss",
     "icon_name": "microwave", "constraint_group": None,
     "preference_weights": {"minimalist": 0.7, "night_owl": 0.3}},
    # Organization
    {"zone": "kitchen", "category": "organization", "name": "Spice Rack",
     "description": "Labeled and organized spice collection",
     "icon_name": "spice_rack", "constraint_group": None,
     "preference_weights": {"cooking": 0.6, "tidiness": 0.7}},
    {"zone": "kitchen", "category": "organization", "name": "Meal Prep Containers",
     "description": "Sunday prep, weekday ease",
     "icon_name": "meal_prep", "constraint_group": None,
     "preference_weights": {"tidiness": 0.7, "wellness": 0.5, "cooking": 0.3}},
    {"zone": "kitchen", "category": "decor", "name": "Chalkboard Menu",
     "description": "Weekly menu or grocery list on the wall",
     "icon_name": "chalkboard_menu", "constraint_group": None,
     "preference_weights": {"creative": 0.5, "cooking": 0.4, "tidiness": 0.3}},
    {"zone": "kitchen", "category": "decor", "name": "Herb Garden",
     "description": "Fresh herbs growing on the windowsill",
     "icon_name": "herb_garden", "constraint_group": None,
     "preference_weights": {"cooking": 0.5, "wellness": 0.4, "outdoorsy": 0.5}},

    # ─── BATHROOM ────────────────────────────────────────────
    # Shower setup (constraint_group: bathroom_shower)
    {"zone": "bathroom", "category": "shower", "name": "Quick Shower",
     "description": "In and out, no nonsense",
     "icon_name": "shower", "constraint_group": "bathroom_shower",
     "preference_weights": {"minimalist": 0.7, "tidiness": 0.3}},
    {"zone": "bathroom", "category": "shower", "name": "Spa Shower",
     "description": "Rain head, eucalyptus, the works",
     "icon_name": "spa_shower", "constraint_group": "bathroom_shower",
     "preference_weights": {"wellness": 0.9, "cozy": 0.4}},
    # Vanity (constraint_group: bathroom_vanity)
    {"zone": "bathroom", "category": "vanity", "name": "Minimal Vanity",
     "description": "Soap, toothbrush, done",
     "icon_name": "minimal_vanity", "constraint_group": "bathroom_vanity",
     "preference_weights": {"minimalist": 0.8, "tidiness": 0.5}},
    {"zone": "bathroom", "category": "vanity", "name": "Skincare Station",
     "description": "Full routine, neatly organized",
     "icon_name": "skincare_station", "constraint_group": "bathroom_vanity",
     "preference_weights": {"wellness": 0.7, "tidiness": 0.5, "creative": 0.2}},
    # Extras
    {"zone": "bathroom", "category": "decor", "name": "Candles & Diffuser",
     "description": "Smells like a spa in here",
     "icon_name": "candle", "constraint_group": None,
     "preference_weights": {"cozy": 0.7, "wellness": 0.5}},
    {"zone": "bathroom", "category": "organization", "name": "Towel Organizer",
     "description": "Rolled towels, labeled shelves",
     "icon_name": "towel_organizer", "constraint_group": None,
     "preference_weights": {"tidiness": 0.9, "minimalist": 0.3}},
    {"zone": "bathroom", "category": "decor", "name": "Bathroom Plants",
     "description": "Humidity-loving plants on the shelf",
     "icon_name": "bathroom_plants", "constraint_group": None,
     "preference_weights": {"wellness": 0.4, "cozy": 0.4, "outdoorsy": 0.3}},
    {"zone": "bathroom", "category": "organization", "name": "Magazine Rack",
     "description": "Reading material for... contemplation",
     "icon_name": "magazine_rack", "constraint_group": None,
     "preference_weights": {"studious": 0.3, "creative": 0.3, "cozy": 0.3}},
]


# ── Style Presets ────────────────────────────────────────────────
# Each preset references furniture by name; IDs are resolved at seed time.

PRESETS: list[dict] = [
    # Bedroom presets
    {"zone": "bedroom", "name": "Minimalist",
     "description": "Clean lines, clear mind",
     "furniture_names": ["Twin Bed", "Study Desk", "Desk Lamp", "Under-Bed Storage"]},
    {"zone": "bedroom", "name": "Cozy Nest",
     "description": "Warm, soft, and inviting",
     "furniture_names": ["Queen Bed", "Fairy Lights", "Plant Collection", "Bookshelf"]},
    {"zone": "bedroom", "name": "Study Cave",
     "description": "Built for focus and deep work",
     "furniture_names": ["Loft Bed", "Study Desk", "Desk Lamp", "Bookshelf"]},
    {"zone": "bedroom", "name": "Night Owl Den",
     "description": "Late nights, creative energy",
     "furniture_names": ["Queen Bed", "Art Desk", "LED Strip Lights", "Poster Wall"]},

    # Living room presets
    {"zone": "living_room", "name": "Hangout Central",
     "description": "Always ready for company",
     "furniture_names": ["Big Couch", "TV Setup", "Gallery Wall", "Shoe Rack"]},
    {"zone": "living_room", "name": "Chill Lounge",
     "description": "Laid-back vibes only",
     "furniture_names": ["Bean Bag Pit", "Record Player", "Indoor Plants"]},
    {"zone": "living_room", "name": "Wellness Studio",
     "description": "Mind and body balance",
     "furniture_names": ["Reading Nook", "Indoor Plants", "Yoga Mat Corner"]},
    {"zone": "living_room", "name": "Game Night HQ",
     "description": "Board games and banter",
     "furniture_names": ["Big Couch", "Board Game Shelf", "Gallery Wall"]},

    # Kitchen presets
    {"zone": "kitchen", "name": "Home Chef",
     "description": "Serious about cooking",
     "furniture_names": ["Espresso Machine", "Cast Iron Set", "Spice Rack", "Herb Garden"]},
    {"zone": "kitchen", "name": "Health Nut",
     "description": "Clean eating, meal prep life",
     "furniture_names": ["Smoothie Blender", "Meal Prep Containers", "Herb Garden"]},
    {"zone": "kitchen", "name": "Keep It Simple",
     "description": "Functional, no frills",
     "furniture_names": ["Tea Station", "Microwave & Ramen", "Meal Prep Containers"]},
    {"zone": "kitchen", "name": "Baker's Kitchen",
     "description": "Flour on the counter, cookies in the oven",
     "furniture_names": ["Tea Station", "Baking Kit", "Spice Rack", "Chalkboard Menu"]},

    # Bathroom presets
    {"zone": "bathroom", "name": "Spa Retreat",
     "description": "Self-care sanctuary",
     "furniture_names": ["Spa Shower", "Skincare Station", "Candles & Diffuser", "Bathroom Plants"]},
    {"zone": "bathroom", "name": "No Fuss",
     "description": "Quick and efficient",
     "furniture_names": ["Quick Shower", "Minimal Vanity", "Towel Organizer"]},
    {"zone": "bathroom", "name": "Plant Oasis",
     "description": "Green and serene",
     "furniture_names": ["Spa Shower", "Minimal Vanity", "Bathroom Plants", "Candles & Diffuser"]},
]


async def seed():
    async with engine.begin() as conn:
        # Clear existing data (idempotent)
        await conn.execute(delete(room_style_presets))
        await conn.execute(delete(furniture_catalog))

        # Insert furniture
        for item in FURNITURE:
            await conn.execute(insert(furniture_catalog).values(**item))

        # Build name→id lookup
        result = await conn.execute(
            select(furniture_catalog.c.id, furniture_catalog.c.name)
        )
        name_to_id = {row.name: row.id for row in result.fetchall()}

        # Insert presets with resolved furniture IDs
        for preset in PRESETS:
            fids = [name_to_id[n] for n in preset["furniture_names"] if n in name_to_id]
            await conn.execute(
                insert(room_style_presets).values(
                    zone=preset["zone"],
                    name=preset["name"],
                    description=preset["description"],
                    furniture_ids=fids,
                )
            )

    print(f"Seeded {len(FURNITURE)} furniture items and {len(PRESETS)} presets.")


if __name__ == "__main__":
    asyncio.run(seed())
