from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.routes import users  # APIRouter with /registerUser, /loginUser, etc
from app.routes import apartments  # APIRouter with /apartments/* endpoints
from app.routes import vibe  # APIRouter with /vibe/* endpoints
from app.routes import scenarios  # APIRouter with /scenarios/* endpoints
from app.routes import discovery  # APIRouter with /discovery/* endpoints
from app.routes import quickpicks  # APIRouter with /interest/* + /quickpicks/* endpoints
from app.routes import households  # APIRouter with /households/* endpoints
from app.routes import messaging  # APIRouter with /ws + /conversations/* endpoints
from app.routes import notifications  # APIRouter with /notifications/* endpoints

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Path("static/avatars").mkdir(parents=True,exist_ok=True)
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://matesv1.netlify.app",
        "http://localhost:3000",
        "http://localhost:8080"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register user routes
app.include_router(users.router)
app.include_router(apartments.router)
app.include_router(vibe.router)
app.include_router(scenarios.router)
app.include_router(discovery.router)
app.include_router(quickpicks.router)
app.include_router(households.router)
app.include_router(messaging.router)
app.include_router(notifications.router)

# Ensure static directory exists before mounting
Path("static").mkdir(parents=True, exist_ok=True)

# Serve local static files at /static
app.mount("/static", StaticFiles(directory="static"), name="static")
