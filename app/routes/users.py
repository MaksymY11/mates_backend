from fastapi import Depends, APIRouter, HTTPException, Request, Body, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, insert
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models import users, refresh_tokens, verification_codes
from app.security import (
    hash_password, 
    verify_password, 
    validate_password_strength, 
    now, 
    generate_code,
    CODE_EXPIRY_MIN
)
from app.limiter import limiter
from app.deps import get_current_user, require_verified_user
from app.auth import (
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
)
from app.email import send_verification_email
from pydantic import BaseModel, EmailStr, Field
import os
import secrets
import asyncio
from io import BytesIO
from datetime import datetime, timedelta, timezone
from PIL import Image
from app.storage import upload_avatar
import logging

_DUMMY_HASH = "$2b$12$LJ3m4ys3Lg2HEAiTL1a5iOsEejlnBMkLCDCySF3GHIV3TfFOOSY0i"

class UserRegister(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

class RefreshRequest(BaseModel):
    refresh_token: str

router = APIRouter()

@router.post("/registerUser")
@limiter.limit("5/15minutes")
async def register_user(request: Request, user: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user. If the email is already registered and verified, returns 409. If it belongs to an                                                                                                                                                                  
    abandoned unverified account, the old row (and its cascaded tokens) is deleted and replaced, letting the user                                                                                                                                                             
    start over without a confusing 409. Stale verification codes are cleared explicitly (no FK cascade). Returns                                                                                                                                                             
    access + refresh tokens plus the email_verified flag, and sends a verification email unless SKIP_EMAIL_VERIFICATION is set."""

    skip = os.getenv("SKIP_EMAIL_VERIFICATION", "").lower() == "true"

    validate_password_strength(user.password)
    hashed_password = hash_password(user.password)

    result = await db.execute(
        select(users)
        .where(users.c.email == user.email)
    )
    existing = result.fetchone()

    if existing and existing.email_verified:
        raise HTTPException(status_code=409, detail="User already exists")

    try:
        # If user already exists
        if existing:
            # Delete user's info from db, and let user re-register
            await db.execute(
                delete(users)
                .where(users.c.email == user.email)
            )
            await db.execute(
                delete(verification_codes)
                .where(verification_codes.c.user_email == user.email)
            )
            # Re-insert
            await db.execute(
                insert(users)
                .values(
                    email=user.email, 
                    password=hashed_password,
                    email_verified=skip
                )
            )
        # If it's a fresh user
        else:
            await db.execute(
                insert(users)
                .values(
                    email=user.email, 
                    password=hashed_password,
                    email_verified=skip
                )
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
    expires_at = now() + timedelta(minutes= REFRESH_TOKEN_EXPIRE_MINUTES)
    await db.execute(
        insert(refresh_tokens).values(
            token = r_token,
            user_email = user.email,
            expires_at = expires_at,
        )
    )
    await db.commit()

    if not skip:
        code = generate_code()
        code_hash = hash_password(code)
        await db.execute(
            insert(verification_codes)
            .values(
                user_email=user.email,
                code_hash=code_hash,
                purpose="email_verification",
                expires_at=now() + timedelta(minutes=CODE_EXPIRY_MIN),
                used=False,
                created_at=now()
            )
        )
        await db.commit()
        await send_verification_email(user.email, code)

    return {
        "access_token": access_token, 
        "refresh_token": r_token, 
        "token_type": "bearer", 
        "email_verified": skip
    }

@router.post("/loginUser")
@limiter.limit("5/15minutes")
async def login_user(request: Request, user: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate credentials and return access + refresh tokens plus email_verified flag (frontend gates on this)."""

    result = await db.execute(
        select(users)
        .where(users.c.email == user.email)
        )
    record = result.fetchone()
    
    if not record:
        verify_password(user.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(user.password, record.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate tokens with expiration
    access_token = create_access_token(
        {"email": record.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    r_token = secrets.token_urlsafe(32)
    expires_at = now() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    await db.execute(
        insert(refresh_tokens).values(
            token= r_token,
            user_email= record.email,
            expires_at= expires_at,
        )
    )
    await db.commit()
    return {
        "access_token": access_token, 
        "refresh_token": r_token, 
        "token_type": "bearer",
        "email_verified": record.email_verified
    }

@router.post("/refreshToken")
@limiter.limit("10/15minutes")
async def refresh_token(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair. Old token is consumed."""

    r_token = body.refresh_token
    
    result = await db.execute(
        select(refresh_tokens).where(refresh_tokens.c.token == r_token)
    )
    record = result.fetchone()
    if not record or record.expires_at < now():
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    await db.execute(
        delete(refresh_tokens).where(refresh_tokens.c.token == r_token)
    )
    new_r_token = secrets.token_urlsafe(32)
    expires_at = now() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
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
    payload: dict = Depends(require_verified_user),
    data: dict = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Update the authenticated user's profile. Unknown or disallowed fields are silently dropped (allowlist enforced server-side)."""

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
async def upload_avatar_endpoint(
    file: UploadFile = File(...),
    payload: dict = Depends(require_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload and validate an avatar image. Converts to JPEG, generates a thumbnail, and uploads both to S3."""

    if file.content_type not in ("image/jpeg", "image/png", "image/gif"):
        raise HTTPException(status_code=400, detail="Unsupported image type")

    MAX_BYTES = 5 * 1024 * 1024
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large")

    try:
        with Image.open(BytesIO(data)) as img:
            rgb = img.convert("RGB")
            full_buf = BytesIO()
            rgb.save(full_buf, format="JPEG", quality=85)
            full_bytes = full_buf.getvalue()

            rgb.thumbnail((200, 200))
            thumb_buf = BytesIO()
            rgb.save(thumb_buf, format="JPEG", quality=85)
            thumb_bytes = thumb_buf.getvalue()
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")

    email = payload["email"]
    result = await db.execute(select(users).where(users.c.email == email))
    row = result.fetchone()

    avatar_url, thumb_url = await asyncio.gather(
        upload_avatar(row.id, full_bytes),
        upload_avatar(row.id, thumb_bytes, suffix="_thumb"),
    )

    await db.execute(
        update(users).where(users.c.email == email).values(
            avatar_url=avatar_url,
            avatar_thumb_url=thumb_url,
        )
    )
    await db.commit()

    return {"avatar_url": avatar_url, "avatar_thumb_url": thumb_url}
