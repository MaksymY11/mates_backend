from fastapi import FastAPI
from app.database import database  # your async Database(...) instance
from app.routes import users  # your APIRouter with /registerUser, /loginUser, etc

app = FastAPI()

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Register your user routes (they use the db via the imported 'database')
app.include_router(users.router)
