from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession                                                                                                                                                                                                                          
from sqlalchemy import select, insert, update, delete
from pydantic import BaseModel, EmailStr, Field
from datetime import timedelta
import logging

from app.database import get_db
from app.models import users, verification_codes, refresh_tokens, device_tokens
from app.security import (
    hash_password, 
    verify_password, 
    validate_password_strength, 
    now, 
    generate_code,
    CODE_EXPIRY_MIN
)
from app.deps import get_current_user
from app.limiter import limiter
from app.email import send_verification_email, send_password_reset_email

logger = logging.getLogger(__name__)

RESEND_COOLDOWN_SEC = 60
_DUMMY_HASH = "$2b$12$LJ3m4ys3Lg2HEAiTL1a5iOsEejlnBMkLCDCySF3GHIV3TfFOOSY0i"

router = APIRouter()

class VerifyEmailRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str

# ── Verification CRUD ──────────────────────────────────────────────────

@router.post("/verifyEmail")
@limiter.limit("5/15minutes")
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Verify the authenticated user's email using a 6-digit code. Marks the code as used and flips email_verified to True."""

    # Get the most recent unused, unexpired email_verification code for this user
    result = await db.execute(
        select(verification_codes.c.code_hash, verification_codes.c.id)
        .where(verification_codes.c.user_email == payload["email"], 
               verification_codes.c.purpose == "email_verification",
               verification_codes.c.used == False,
               verification_codes.c.expires_at > now()
               )
        .order_by(verification_codes.c.created_at.desc())
    )
    record = result.fetchone()
    if not record or not verify_password(body.code, record.code_hash):
        raise HTTPException(status_code=400, detail="Incorrect verification code.")
    
    await db.execute(
        update(verification_codes)
        .where(verification_codes.c.id == record.id)
        .values(used=True)
    )

    await db.execute(
        update(users)
        .where(users.c.email == payload["email"])
        .values(email_verified=True)
    )

    await db.commit()
    return {"detail": "Email verified."}

@router.post("/resendVerification")
@limiter.limit("5/15minutes")
async def resend_verification(
    request: Request,
    payload: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Issue a new verification code for the authenticated user. Enforces a 60s resend cooldown and 400s if already verified."""

    result = await db.execute(
        select(users.c.email_verified)
        .where(users.c.email == payload["email"])
    )
    record = result.fetchone()
    if record and record.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified.")
    
    result = await db.execute(
        select(verification_codes.c.created_at)
        .where(verification_codes.c.user_email == payload["email"],
               verification_codes.c.purpose == "email_verification")
        .order_by(verification_codes.c.created_at.desc())
        .limit(1)
    )
    record = result.fetchone()
    if record:
        elapsed = (now() - record.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SEC:
            remaining = int(RESEND_COOLDOWN_SEC - elapsed)
            raise HTTPException(status_code=429, detail=f"Please wait {remaining} seconds before requesting another code.")
        
    code = generate_code()
    code_hash = hash_password(code)
    await db.execute(
        insert(verification_codes)
        .values(
            user_email=payload["email"],
            code_hash=code_hash,
            purpose="email_verification",
            expires_at=now()+timedelta(minutes=CODE_EXPIRY_MIN),
            used=False,
            created_at=now()
        )
    )
    await db.commit()

    await send_verification_email(payload["email"],code)

    return {"detail": "Verification code sent."}

@router.post("/forgotPassword")
@limiter.limit("3/15minutes")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Send a password reset code if the email is registered. Always returns 200 to prevent user enumeration."""

    result = await db.execute(
        select(users.c.email)
        .where(users.c.email == body.email.lower())
    )
    record = result.fetchone()
    if record:
        code = generate_code()
        code_hash = hash_password(code)
        await db.execute(
            insert(verification_codes)
            .values(
                user_email=record.email,
                code_hash=code_hash,
                purpose="password_reset",
                expires_at=now()+timedelta(minutes=CODE_EXPIRY_MIN),
                used=False,
                created_at=now()
            )
        )
        await db.commit()

        await send_password_reset_email(record.email, code)
    else:
        verify_password("dummy", _DUMMY_HASH)

    return {"detail": "If that email is registered, a reset code has been sent."}

@router.post("/resetPassword")
@limiter.limit("5/15minutes")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset password using a 6-digit code sent via /forgotPassword. Validates the code, updates the password, and
    flips email_verified to True, receiving the code at the user's inbox is proof of email ownership, same as the
    verification flow. Invalidates all refresh tokens and device tokens (logs user out everywhere)."""

    user_email = body.email.lower()
    validate_password_strength(body.new_password)

    result = await db.execute(
        select(verification_codes.c.code_hash, verification_codes.c.id)
        .where(verification_codes.c.user_email == user_email, 
               verification_codes.c.purpose == "password_reset",
               verification_codes.c.used == False,
               verification_codes.c.expires_at > now()
               )
        .order_by(verification_codes.c.created_at.desc())
    )
    code_record = result.fetchone()
    if not code_record or not verify_password(body.code, code_record.code_hash):
        raise HTTPException(status_code=400, detail="Incorrect verification code.")
    
    # Grab user's id
    result = await db.execute(
        select(users.c.id, users.c.password)
        .where(users.c.email == user_email)
    )
    user_record = result.fetchone()
    if not user_record:
        logger.error("User %s vanished between code validation and password update", user_email)
        raise HTTPException(status_code=400, detail="Incorrect verification code.")
    
    if verify_password(body.new_password, user_record.password):
        raise HTTPException(status_code=400, detail="New password must be different from your current password.")
    
    # Update "used" value
    await db.execute(
        update(verification_codes)
        .where(verification_codes.c.id == code_record.id)
        .values(used=True)
    )

    # Update new password and set email_verified to True because resetting password proves ownership
    await db.execute(
        update(users)
        .where(users.c.id == user_record.id)
        .values(password=hash_password(body.new_password), email_verified=True)
    )

    # Query to delete all refresh and device tokens -> logs user out of all devices.
    await db.execute(
        delete(refresh_tokens)
        .where(refresh_tokens.c.user_email == user_email)
    )
    await db.execute(
        delete(device_tokens)
        .where(device_tokens.c.user_id == user_record.id)
    )

    await db.commit()
    return {"detail": "Password reset successfully."}