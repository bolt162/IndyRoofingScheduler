"""
Activity log: one clean, admin-only record of what the platform does.

Stored in the activity_log table (Railway's disk is wiped on every deploy, so a file
wouldn't survive). Kept small on purpose:

  - Each scheduled job run and each user action is ONE row, with totals of the outside
    calls it made ("JobNimbus 118, Claude 2, 3.4s").
  - Errors, emails, and notes written to JobNimbus each get their own row.
  - No secrets, no message bodies: API keys and tokens are scrubbed from any text.
  - Rows older than RETENTION_DAYS are pruned daily.

Logging must never break the app: every write is isolated in its own session and
wrapped so failures are swallowed.
"""
import contextvars
import functools
import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base

logger = logging.getLogger("activity")

RETENTION_DAYS = 90


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # user (someone clicked something), job (automatic run), email, note (written to
    # JobNimbus), error, api (an outside call made outside any run)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok / error / skipped
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ---------------------------------------------------------------------------
# Scrubbing
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    # key=VALUE / token: VALUE style (keep the name, hide the value)
    (re.compile(r"(?i)\b(key|api[_-]?key|secret|token|password|pass|authorization)(\s*[=:]\s*)[^&\s,'\"]+"), r"\1\2[hidden]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer [hidden]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "[hidden]"),
]


def scrub(text: str | None, limit: int = 500) -> str | None:
    if text is None:
        return None
    s = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        s = pattern.sub(replacement, s)
    s = " ".join(s.split())
    return s[:limit]


# ---------------------------------------------------------------------------
# Runs: collect outside-call totals for one job run or one request
# ---------------------------------------------------------------------------

class Run:
    def __init__(self, kind: str, source: str, action: str, actor: str | None = None):
        self.kind, self.source, self.action, self.actor = kind, source, action, actor
        self.started = time.monotonic()
        self.calls: dict[str, list[int]] = {}  # source -> [calls, errors]
        self.lock = threading.Lock()
        self.force_error = False  # e.g. the request itself returned 4xx/5xx
        self.job_id: int | None = None

    def add(self, source: str, ok: bool) -> None:
        with self.lock:
            c = self.calls.setdefault(source, [0, 0])
            c[0] += 1
            if not ok:
                c[1] += 1

    def summary(self) -> str:
        parts = []
        for source, (n, errs) in sorted(self.calls.items()):
            parts.append(f"{LABELS.get(source, source)} {n}" + (f" ({errs} failed)" if errs else ""))
        return ", ".join(parts)

    def errors(self) -> int:
        return sum(e for _, e in self.calls.values())

    def ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)


LABELS = {"jobnimbus": "JobNimbus", "claude": "Claude", "google_maps": "Google Maps",
          "open_meteo": "Open-Meteo", "claritywx": "ClarityWx", "smtp": "Email"}

_current: contextvars.ContextVar[Run | None] = contextvars.ContextVar("activity_run", default=None)


def current_run() -> Run | None:
    return _current.get()


# ---------------------------------------------------------------------------
# Writing rows
# ---------------------------------------------------------------------------

def write(kind: str, source: str, action: str, status: str = "ok", actor: str | None = None,
          job_id: int | None = None, duration_ms: int | None = None, detail: str | None = None) -> None:
    """Write one row in its own session. Never raises."""
    try:
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            db.add(ActivityLog(kind=kind, source=source[:40], action=scrub(action, 160), status=status,
                               actor=(actor or None) and actor[:255], job_id=job_id,
                               duration_ms=duration_ms, detail=scrub(detail)))
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"activity write failed: {e}")


@contextmanager
def run(kind: str, source: str, action: str, actor: str | None = None, always: bool = True):
    """
    Group everything inside into one row. With always=False the row is only written if
    the run made outside calls or failed (used for read-only page loads).
    """
    r = Run(kind, source, action, actor)
    token = _current.set(r)
    failed: Exception | None = None
    try:
        yield r
    except Exception as e:
        failed = e
        raise
    finally:
        _current.reset(token)
        if always or r.calls or failed:
            status = "error" if (failed or r.errors() or r.force_error) else "ok"
            detail = r.summary()
            if failed:
                detail = f"{type(failed).__name__}: {failed}" + (f" | {detail}" if detail else "")
            # Read from the run, not the arguments: the request logger fills in the route,
            # result code, and who did it after the request finishes
            write(r.kind, r.source, r.action, status=status, actor=r.actor, job_id=r.job_id,
                  duration_ms=r.ms(), detail=detail or None)


def job_run(name: str):
    """Decorator for scheduled jobs: one row per run."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            with run("job", "scheduler", name):
                return fn(*args, **kwargs)
        return inner
    return wrap


def record_call(source: str, action: str, ok: bool, detail: str | None = None, duration_ms: int | None = None) -> None:
    """An outside call finished. Counted into the current run; failures also get a row."""
    r = current_run()
    if r is not None:
        r.add(source, ok)
        if not ok:
            write("error", source, action, status="error", actor=r.actor, duration_ms=duration_ms,
                  detail=f"during {r.action}: {detail or ''}")
        return
    write("api" if ok else "error", source, action, status="ok" if ok else "error",
          duration_ms=duration_ms, detail=detail)


@contextmanager
def call(source: str, action: str):
    """Time an outside call that isn't plain httpx (Claude, SMTP)."""
    start = time.monotonic()
    try:
        yield
    except Exception as e:
        record_call(source, action, False, f"{type(e).__name__}: {e}", int((time.monotonic() - start) * 1000))
        raise
    record_call(source, action, True, None, int((time.monotonic() - start) * 1000))


def bind_context(fn):
    """
    Carry the current run into worker threads (ThreadPoolExecutor drops contextvars).
    Each call sets the run itself; one shared copied Context can't be entered by two
    threads at once, which crashed overlapping JobNimbus lookups.
    """
    parent = current_run()

    def inner(*a, **k):
        token = _current.set(parent)
        try:
            return fn(*a, **k)
        finally:
            _current.reset(token)
    return inner


# ---------------------------------------------------------------------------
# httpx: every outside HTTP call in the app goes through httpx.get / httpx.post
# ---------------------------------------------------------------------------

HOSTS = {
    "app.jobnimbus.com": "jobnimbus",
    "maps.googleapis.com": "google_maps",
    "api.open-meteo.com": "open_meteo",
    "api.claritywx.com": "claritywx",
}
_ID = re.compile(r"/[0-9a-f\-]{16,}|/\d{3,}", re.I)


def _describe(method: str, url: str) -> tuple[str, str]:
    u = urlparse(str(url))
    host = (u.hostname or "").lower()
    source = HOSTS.get(host) or ("claritywx" if "claritywx" in host else host or "http")
    path = _ID.sub("/{id}", u.path or "/")
    return source, f"{method} {path}"


_installed = False


def install_http_recorder() -> None:
    """Wrap httpx.get/post once so every outside HTTP call is counted. Idempotent."""
    global _installed
    if _installed:
        return
    import httpx

    def wrap(method_name, original):
        @functools.wraps(original)
        def recorded(url, *args, **kwargs):
            source, action = _describe(method_name.upper(), url)
            start = time.monotonic()
            try:
                resp = original(url, *args, **kwargs)
            except Exception as e:
                record_call(source, action, False, f"{type(e).__name__}: {e}", int((time.monotonic() - start) * 1000))
                raise
            ok = resp.status_code < 400
            record_call(source, action, ok, None if ok else f"HTTP {resp.status_code}",
                        int((time.monotonic() - start) * 1000))
            return resp
        recorded.__activity_wrapped__ = True
        return recorded

    for name in ("get", "post", "put", "patch", "delete"):
        original = getattr(httpx, name)
        if not getattr(original, "__activity_wrapped__", False):
            setattr(httpx, name, wrap(name, original))
    _installed = True


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def prune(days: int = RETENTION_DAYS) -> int:
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        n = db.query(ActivityLog).filter(ActivityLog.at < datetime.utcnow() - timedelta(days=days)).delete()
        db.commit()
        return n
    finally:
        db.close()
