"""
One-click opt-out link for customer emails.

The link carries the job id and a signature, so it can't be guessed or tampered with.
Clicking it marks the job's email state suppressed (reason "unsubscribed") in both modes.

No setup needed: the signing secret comes from EMAIL_UNSUBSCRIBE_SECRET if set, otherwise
one is generated once and kept in system settings. The link points at
EMAIL_PUBLIC_BASE_URL, defaulting to the scheduler's own address.
"""
import hashlib
import hmac
import os
import secrets

DEFAULT_BASE_URL = "https://indyscheduler.top"
SECRET_KEY = "email_unsubscribe_secret"
_cached: bytes | None = None


def _secret() -> bytes:
    global _cached
    env = os.getenv("EMAIL_UNSUBSCRIBE_SECRET", "")
    if env:
        return env.encode()
    if _cached:
        return _cached
    from backend.database import SessionLocal
    from backend.models.settings import SystemSettings
    db = SessionLocal()
    try:
        row = db.query(SystemSettings).filter(SystemSettings.key == SECRET_KEY).first()
        if row is None:
            row = SystemSettings(key=SECRET_KEY, value=secrets.token_hex(32),
                                 description="Signs customer email opt-out links (generated automatically)")
            db.add(row)
            db.commit()
        _cached = row.value.encode()
        return _cached
    finally:
        db.close()


def _base_url() -> str:
    return (os.getenv("EMAIL_PUBLIC_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def token_for(job_id: int) -> str:
    return hmac.new(_secret(), f"unsubscribe:{job_id}".encode(), hashlib.sha256).hexdigest()[:32]


def link_for(job_id: int) -> str | None:
    try:
        return f"{_base_url()}/api/email/unsubscribe?job={job_id}&t={token_for(job_id)}"
    except Exception:  # noqa: BLE001  (never block an email over the opt-out link)
        return None


def valid(job_id: int, token: str) -> bool:
    return hmac.compare_digest(token_for(job_id), token or "")
