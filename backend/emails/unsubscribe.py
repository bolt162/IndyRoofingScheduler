"""
One-click opt-out link for customer emails.

The link carries the job id and a signature, so it can't be guessed or tampered with.
Clicking it marks the job's email state suppressed (reason "unsubscribed") in both modes.
The link is only added once EMAIL_PUBLIC_BASE_URL and EMAIL_UNSUBSCRIBE_SECRET are set.
"""
import hashlib
import hmac
import os


def _secret() -> bytes:
    return os.getenv("EMAIL_UNSUBSCRIBE_SECRET", "").encode()


def _base_url() -> str:
    return os.getenv("EMAIL_PUBLIC_BASE_URL", "").rstrip("/")


def token_for(job_id: int) -> str:
    return hmac.new(_secret(), f"unsubscribe:{job_id}".encode(), hashlib.sha256).hexdigest()[:32]


def link_for(job_id: int) -> str | None:
    if not _secret() or not _base_url():
        return None
    return f"{_base_url()}/api/email/unsubscribe?job={job_id}&t={token_for(job_id)}"


def valid(job_id: int, token: str) -> bool:
    return bool(_secret()) and hmac.compare_digest(token_for(job_id), token or "")
