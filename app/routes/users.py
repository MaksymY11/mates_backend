from fastapi import Depends, APIRouter, HTTPException, Request, Body, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, insert
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import users, refresh_tokens
from app.security import hash_password, verify_password
from app.limiter import limiter
from app.deps import get_current_user
from app.auth import (
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
)
from pydantic import BaseModel, EmailStr, Field
import os
import secrets
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from PIL import Image, UnidentifiedImageError
import aiofiles
import logging

# Use a local writable static folder by default so avatars persist locally.
# Set `BASE_URL` in your env (e.g. https://example.com) to return full URLs;
# otherwise a relative path will be returned (served from /static).
AVATAR_DIR = Path("static/avatars")  # local relative to project root
BASE_URL = os.getenv("BASE_URL", "").strip()
_DUMMY_HASH = "$2b$12$LJ3m4ys3Lg2HEAiTL1a5iOsEejlnBMkLCDCySF3GHIV3TfFOOSY0i"

if BASE_URL:
    AVATAR_URL_PREFIX = BASE_URL.rstrip("/") + "/static/avatars"
else:
    AVATAR_URL_PREFIX = "/static/avatars"

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

class RefreshRequest(BaseModel):
    refresh_token: str

router = APIRouter()

@router.post("/registerUser")
@limiter.limit("5/15minutes")
async def register_user(request: Request, user: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user and return access + refresh tokens."""

    # user.email and user.password (dot notation)
    hashed_password = hash_password(user.password)
    try:
        await db.execute(
            insert(users).values(email=user.email, password=hashed_password)
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="User already exists")
    
    # Auto login after registration
    access_token = create_access_token(
        {"email" : user.email},
        expires_delta= timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    r_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes= REFRESH_TOKEN_EXPIRE_MINUTES)
    await db.execute(
        insert(refresh_tokens).values(
            token = r_token,
            user_email = user.email,
            expires_at = expires_at,
        )
    )
    await db.commit()
    return {"access_token": access_token, "refresh_token": r_token, "token_type": "bearer"}

@router.post("/loginUser")
@limiter.limit("5/15minutes")
async def login_user(request: Request, user: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate user credentials and return access + refresh tokens."""

    result = await db.execute(select(users).where(users.c.email == user.email))
    db_user = result.fetchone()
    
    if not db_user:
        verify_password(user.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate tokens with expiration
    access_token = create_access_token(
        {"email": db_user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    r_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await db.execute(
        insert(refresh_tokens).values(
            token= r_token,
            user_email= db_user.email,
            expires_at= expires_at,
        )
    )
    await db.commit()
    return {"access_token": access_token, "refresh_token": r_token, "token_type": "bearer"}

@router.post("/refreshToken")
@limiter.limit("10/15minutes")
async def refresh_token(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair. Old token is consumed."""

    r_token = body.refresh_token
    
    result = await db.execute(
        select(refresh_tokens).where(refresh_tokens.c.token == r_token)
    )
    record = result.fetchone()
    if not record or record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    await db.execute(
        delete(refresh_tokens).where(refresh_tokens.c.token == r_token)
    )
    new_r_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await db.execute(
        insert(refresh_tokens).values(
            token= new_r_token,
            user_email= record.user_email,
            expires_at= expires_at,
        )
    )
    await db.commit()
    new_access_token = create_access_token({"email": record.user_email})

    return {"access_token": new_access_token, "refresh_token": new_r_token, "token_type": "bearer"}


@router.post("/logout")
@limiter.limit("5/15minutes")
async def logout(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Invalidate the provided refresh token."""

    r_token = body.refresh_token
    await db.execute(
        delete(refresh_tokens).where(refresh_tokens.c.token == r_token)
    )
    await db.commit()
    return {"detail": "logged out"}

# Returning logged-in user's profile data
@router.get("/me")
async def get_me(payload: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return the authenticated user's profile (excludes password hash)."""
    
    email = payload["email"]
    result = await db.execute(select(users).where(users.c.email == email))
    record = result.fetchone()
    if not record:
        raise HTTPException(status_code=404, detail="User not found")
    data = dict(record._mapping)
    data.pop("password", None) # prevent leaking bcrypt hash
    return data
    
    
@router.post("/updateUser")
async def update_user(
    payload: dict = Depends(get_current_user),
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Update allowed profile fields for the authenticated user."""

    email = payload["email"]

    # filter allowed fields
    allowed = {"name", "city", "bio", "age", "state", "budget", "move_in_date", "lifestyle", "activities", "prefs", "location_preference"}
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

    await db.execute(
        update(users).where(users.c.email == email).values(**update_data)
    )
    await db.commit()
    return {"detail": "Profile updated successfully"}

@router.post("/uploadAvatar")
async def upload_avatar(
    file: UploadFile = File(...),
    request: Request = None,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload and validate an avatar image. Generates a thumbnail and cleans up the previous avatar."""
    
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
                        logging.warning("Failed to close temp file handle during size check", exc_info=True)
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
        except Exception:
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
        except Exception:
            logging.warning("Thumbnail creation failed for %s", filename, exc_info=True)

        # update user's avatar_url in DB, but first remember previous avatar to delete
        email = payload["email"]
        # fetch existing avatar_url
        result = await db.execute(select(users).where(users.c.email == email))
        row = result.fetchone()
        prev_avatar = row.avatar_url if row else None

        try:
            await db.execute(
                update(users).where(users.c.email == email).values(avatar_url=avatar_url)
            )
            await db.commit()
        except Exception:
            # rollback - delete the newly written file
            try:
                target.unlink(missing_ok=True)
            except Exception:
                logging.exception("Failed to clean up uploaded file %s", target)
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
                logging.warning("Failed to delete previous avatar %s", prev_fname)

        return {"avatar_url": avatar_url, "avatar_thumb_url": thumb_url}
    finally:
        # ensure UploadFile resources are closed
        try:
            await file.close()
        except Exception:
            logging.warning("Failed to close upload file handle", exc_info=True)
