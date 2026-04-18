import os
import logging
import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
FROM_EMAIL = "onboarding@resend.dev"

# ── Helpers ──────────────────────────────────────────────────────

async def _send(to_email: str, subject: str, html: str) -> bool:
    """Send an HTML email via Resend. Returns False on missing API key or HTTP failure (never raises - callers decide how to handle failure)."""

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not set, skipping email to %s", to_email)
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": FROM_EMAIL,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        # CHANGE BACK TO logger.error("Failed to send email to %s: %s", to_email, e)
        print(f"Resend error {e.response.status_code}: {e.response.text}") 
        return False

# ── Public Methods ────────────────────────────────────────────────

async def send_verification_email(to_email: str, code: str) -> bool:
    """Send a 6-digit email verification code. Returns True on success, False if email delivery failed (account creation should still proceed - user can request resend)."""

    subject = "Verify your Mates email"
    html = f"""
    <div style="font-family: sans-serif; max-width:480px; margin:0 auto;">
        <h2 style="color: #4CAF50;">Welcome to Mates</h2>
        <p>Your verification code is:</p>
        <div style="font-size: 32px; letter-spacing: 8px; font-weight: bold; color: #4CAF50; padding: 16px; background: #f5f5f5; text-align: center; border-radius: 8px;">{code}</div>
        <p style="color: #666; font-size: 14px;">This code expires in 10 minutes.</p>
    </div>
    """
    return await _send(to_email, subject, html)


async def send_password_reset_email(to_email: str, code: str) -> bool:
    """Send a 6-digit password reset code. Returns True on success, False if delivery failed (caller should swallow silently for anti-enumeration)."""

    subject = "Reset your Mates password"
    html = f"""
    <div style="font-family: sans-serif; max-width:480px; margin:0 auto;">
        <h2 style="color: #4CAF50;">Password reset</h2>
        <p>Use this code to reset your password:</p>
        <div style="font-size: 32px; letter-spacing: 8px; font-weight: bold; color: #4CAF50; padding: 16px; background: #f5f5f5; text-align: center; border-radius: 8px;">{code}</div>
        <p style="color: #666; font-size: 14px;">This code expires in 10 minutes. If you didn't request this, ignore this email.</p>
    </div>
    """
    return await _send(to_email, subject, html)
