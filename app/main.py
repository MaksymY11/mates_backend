from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.database import database  # your async Database(...) instance
from app.routes import users  # your APIRouter with /registerUser, /loginUser, etc

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or use ["https://685357a1d86235357f60edb5--matesv1.netlify.app"] in prod!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Ensure static folders exist for local avatar storage
    Path("static/avatars").mkdir(parents=True, exist_ok=True)
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Register your user routes (they use the db via the imported 'database')
app.include_router(users.router)

# Serve local static files at /static (files under project `static/`)
app.mount("/static", StaticFiles(directory="static"), name="static")
