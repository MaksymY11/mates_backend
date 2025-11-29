from fastapi import Depends, APIRouter, HTTPException, Response, Request, Body, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.database import database
from app.models import users, refresh_tokens
from passlib.context import CryptContext
from app.auth import (
    create_access_token,
    verify_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
)
from pydantic import BaseModel
import os
import secrets
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, UnidentifiedImageError
import aiofiles

# Use a local writable static folder by default so avatars persist locally.
# Set `BASE_URL` in your env (e.g. https://example.com) to return full URLs;
# otherwise a relative path will be returned (served from /static).
AVATAR_DIR = Path("static/avatars")  # local relative to project root
BASE_URL = os.getenv("BASE_URL", "").strip()
if BASE_URL:
    AVATAR_URL_PREFIX = BASE_URL.rstrip("/") + "/static/avatars"
else:
    AVATAR_URL_PREFIX = "/static/avatars"

# Determine if debug endpoints should be available
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

class UserRegister(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

@router.post("/registerUser")
async def register_user(user: UserRegister):
    # user.email and user.password (dot notation)
    hashed_password = pwd_context.hash(user.password)
    query = users.insert().values(email=user.email, password=hashed_password)
    try:
        await database.execute(query)
        return {"msg": "User created"}
    except Exception:
        raise HTTPException(status_code=400, detail="User already exists")

@router.post("/loginUser")
async def login_user(user: UserLogin, response: Response):
    query = users.select().where(users.c.email == user.email)
    db_user = await database.fetch_one(query)
    if not db_user or not pwd_context.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate tokens with expiration
    access_token = create_access_token(
        {"email": db_user["email"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    r_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await database.execute(
        refresh_tokens.insert().values(
            token=r_token,
            user_email=db_user["email"],
            expires_at=expires_at,
        )
    )
    response.set_cookie(
        "refresh_token",
        r_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refreshToken")
async def refresh_token(request: Request, response: Response):
    r_token = request.cookies.get("refresh_token")
    if not r_token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    record = await database.fetch_one(
        refresh_tokens.select().where(refresh_tokens.c.token == r_token)
    )
    if not record or record["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    await database.execute(
        refresh_tokens.delete().where(refresh_tokens.c.token == r_token)
    )
    new_r_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await database.execute(
        refresh_tokens.insert().values(
            token=new_r_token,
            user_email=record["user_email"],
            expires_at=expires_at,
        )
    )
    new_access_token = create_access_token({"email": record["user_email"]})
    response.set_cookie(
        "refresh_token",
        new_r_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    r_token = request.cookies.get("refresh_token")
    if r_token:
        await database.execute(
            refresh_tokens.delete().where(refresh_tokens.c.token == r_token)
        )
    response.delete_cookie("refresh_token")
    return {"detail": "logged out"}

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    token = credentials.credentials
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload


@router.get("/me")
async def get_me(payload: dict = Depends(get_current_user)):
    email = payload["email"]
    query = users.select().where(users.c.email == email)
    record = await database.fetch_one(query)
    if not record:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(record)
    
if DEBUG_MODE:
    @router.get("/debug/users")
    async def debug_list_users(payload: dict = Depends(get_current_user)):
        rows = await database.fetch_all("SELECT id, email, password FROM users;")
        return [dict(row) for row in rows]
    
@router.post("/updateUser")
async def update_user(
    payload: dict = Depends(get_current_user),
    data: dict = Body(...),
):
    email = payload["email"]

    # filter allowed fields
    allowed = {"name", "city", "bio", "age", "state", "budget", "move_in_date", "lifestyle", "activities", "prefs"}
    update_data = {k: v for k, v in data.items() if k in allowed}

    if "move_in_date" in update_data:
        v = update_data["move_in_date"]
        if isinstance(v, str):
            try:
                parsed = datetime.fromisoformat(v)
                update_data["move_in_date"] = parsed.date()
            except ValueError:
                update_data.pop("move_in_date")  # remove invalid date

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # dynamically build SET clause
    query = users.update().where(users.c.email == email).values(**update_data)
    await database.execute(query)
    return {"detail": "Profile updated successfully"}

@router.post("/uploadAvatar")
async def upload_avatar(
    file: UploadFile = File(...),
    request: Request = None,
    payload: dict = Depends(get_current_user),
):
    # Basic client-provided MIME check (still validate content below)
    if file.content_type not in ("image/jpeg", "image/png", "image/gif"):
        raise HTTPException(status_code=400, detail="Unsupported image type")

    MAX_BYTES = 5 * 1024 * 1024

    # Ensure avatar dir exists
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    # Stream upload to a temporary file to avoid loading whole file into memory
    tmp_name = f"tmp_{uuid.uuid4().hex}"
    tmp_path = AVATAR_DIR / tmp_name
    total = 0
    try:
        async with aiofiles.open(tmp_path, "wb") as afp:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    # cleanup
                    try:
                        await afp.close()
                    except Exception:
                        pass
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="File too large")
                await afp.write(chunk)

        # Validate image file using Pillow to avoid spoofed content-type
        try:
            with Image.open(tmp_path) as img:
                img.verify()
                fmt = img.format  # e.g. 'JPEG', 'PNG', 'GIF'
        except UnidentifiedImageError:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Invalid image file")

        fmt = (fmt or "JPEG").upper()
        ext_map = {"JPEG": ".jpg", "JPG": ".jpg", "PNG": ".png", "GIF": ".gif"}
        ext = ext_map.get(fmt, Path(file.filename).suffix or ".jpg")

        filename = f"{uuid.uuid4().hex}{ext}"
        target = AVATAR_DIR / filename

        # Move temp file into final filename (atomic on most OSes)
        tmp_path.replace(target)

        # Build avatar URL: prefer configured BASE_URL, otherwise use request.base_url
        prefix = AVATAR_URL_PREFIX
        if not BASE_URL and request is not None:
            base = str(request.base_url).rstrip("/")
            prefix = base + "/static/avatars"
        avatar_url = f"{prefix}/{filename}"

        # create a thumbnail (small size) to serve to mobile clients and save alongside
        thumb_url = None
        try:
            # Re-open the file to create thumbnail (verify() closed the previous handle)
            with Image.open(target) as im:
                thumb_size = (200, 200)
                thumb_name = f"{Path(filename).stem}_thumb.jpg"
                thumb_path = AVATAR_DIR / thumb_name
                im_rgb = im.convert("RGB")
                im_rgb.thumbnail(thumb_size)
                im_rgb.save(thumb_path, format="JPEG", quality=85)
                thumb_url = f"{prefix}/{thumb_name}"
        except Exception as thumb_err:
            # Thumbnailing is non-critical, log and continue
            pass

        # update user's avatar_url in DB, but first remember previous avatar to delete
        email = payload["email"]
        # fetch existing avatar_url
        row = await database.fetch_one(users.select().where(users.c.email == email))
        prev_avatar = row.get("avatar_url") if row else None

        try:
            await database.execute(
                users.update().where(users.c.email == email).values(avatar_url=avatar_url)
            )
        except Exception:
            # rollback - delete the newly written file
            try:
                target.unlink(missing_ok=True)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail="Failed to update avatar")

        # Delete previous avatar file if it was stored locally under our static folder
        if prev_avatar:
            try:
                # prev_avatar may be absolute URL or relative path; extract filename if it points to /static/avatars
                if prev_avatar.startswith(AVATAR_URL_PREFIX) or prev_avatar.startswith("/static/avatars"):
                    prev_fname = Path(prev_avatar).name
                    prev_path = AVATAR_DIR / prev_fname
                    if prev_path.exists():
                        prev_path.unlink(missing_ok=True)
            except Exception:
                # non-fatal cleanup error
                pass

        return {"avatar_url": avatar_url, "avatar_thumb_url": thumb_url}
    finally:
        # ensure UploadFile resources are closed
        try:
            await file.close()
        except Exception:
            pass
