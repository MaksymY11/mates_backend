import firebase_admin
from firebase_admin import credentials, messaging
import os

_cred_path = os.path.join(os.path.dirname(__file__), "..", "firebase-service-account.json")

_initialized = False


def _ensure_init():
    global _initialized
    if _initialized:
        return
    if os.path.exists(_cred_path):
        cred = credentials.Certificate(_cred_path)
        firebase_admin.initialize_app(cred)
        _initialized = True
    else:
        print("[FIREBASE] Service account key not found — push notifications disabled")


def send_push(token: str, title: str, body: str, data: dict | None = None) -> bool | None:
    """Send a single FCM push notification. Returns True on success, False if token is stale (should delete), None on transient error."""
    _ensure_init()
    if not _initialized:
        return None
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        messaging.send(message)
        return True
    except messaging.UnregisteredError:
        return False
    except Exception as e:
        print(f"[FIREBASE] Push failed for token {token[:20]}...: {e}")
        return None
