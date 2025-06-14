from fastapi import FastAPI
from databases import Database

app = FastAPI()
database = Database(DATABASE_URL)  # however you pull in your URL

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/debug/tables")
async def list_tables():
    # Query Postgres metadata for public tables
    rows = await database.fetch_all("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    return [r["table_name"] for r in rows]
