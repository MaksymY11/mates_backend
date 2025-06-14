import os
from fastapi import FastAPI
from databases import Database

app = FastAPI()
database = Database(os.getenv("DATABASE_URL"))

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

@app.get("/debug/info")
async def debug_info():
    # List tables
    tables = await database.fetch_all("""
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name;
    """)
    # Check current database
    current_db = await database.fetch_one("SELECT current_database() AS db")
    return {
      "DATABASE_URL": os.getenv("DATABASE_URL"),
      "current_database": current_db["db"],
      "tables": [r["table_name"] for r in tables],
    }
