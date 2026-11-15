"""
Automatic retry for runs that sent some or all of their emails badly (Aaron, 2026-11-14).

When the Thursday run, the Welcome run, the ABC delivery reminder or a weather report to Greg and Luke fails
for anyone, the Scheduler tries again about 30 minutes later, up to 2 times per run per Indianapolis day
(the weather report: once). The pending retry is saved in the settings table, so a restart or deploy inside
those 30 minutes still runs it.

Retries never double-send, because they run the very same code as the normal run: progress is saved only for
emails that really went, and the selector skips anyone already emailed (Thursday: since Thursday 12:00 AM
Indianapolis; Welcome: welcome_sent; ABC: a reminder that really went today).

Alerts: at most one per attempt, and the quiet middle attempt sends none. The first failure tells Aaron when it
will try again; the last failure tells him what is left and that Claude can run it again.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

logger = logging.getLogger("emails.retry")

TZ = ZoneInfo("America/Indiana/Indianapolis")
RETRY_DELAY = timedelta(minutes=30)
MAX_RETRIES = 2
WEATHER_MAX_RETRIES = 1
IN_PROGRESS = timedelta(minutes=15)      # a retry that began this recently is still running
RESUME_DELAY = timedelta(minutes=5)      # after a restart, let the Thursday catch-up (3 minutes) go first
PREFIX = "email_retry_"

# Saved retry name -> the function in backend/emails/runner.py it runs again
EMAIL_RUNS = {"weekly": "run_weekly", "welcomes": "run_welcomes", "abc_daily": "run_abc_daily"}

_scheduler = None   # set by main.py once APScheduler is running


@dataclass
class Plan:
    """What a failed attempt decided. retry_at is naive UTC (how times are stored)."""
    retry_at: datetime | None = None
    final: bool = False
    alert: bool = True

    @property
    def retry_time(self) -> str:
        return clock_words(self.retry_at) if self.retry_at else ""


def clock_words(utc_naive: datetime) -> str:
    """'10:35 AM' in Indianapolis time."""
    local = utc_naive.replace(tzinfo=timezone.utc).astimezone(TZ)
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def _indy_day(utc_naive: datetime) -> str:
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(TZ).date().isoformat()


def _state_mode(mode: str) -> str:
    return "test" if mode == "test" else "live"


def _key(mode: str, run: str) -> str:
    return f"{PREFIX}{_state_mode(mode)}_{run}"


def _get_setting(db: Session, key: str) -> str | None:
    from backend.models.settings import SystemSettings
    row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return row.value if row else None


def _put_setting(db: Session, key: str, value: str) -> None:
    from backend.models.settings import SystemSettings
    row = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSettings(key=key, value=value, description="Pending automatic retry of a failed email run"))
    db.commit()


def _parse(raw: str | None) -> dict:
    try:
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def load(db: Session, run: str, mode: str, now: datetime) -> dict:
    """Today's saved retry record for this run (empty when there is none, or it is from an earlier day)."""
    data = _parse(_get_setting(db, _key(mode, run)))
    return data if data.get("day") == _indy_day(now) else {}


def _save(db: Session, run: str, mode: str, now: datetime, done: int, due: datetime | None,
          started: datetime | None = None, payload: dict | None = None) -> None:
    _put_setting(db, _key(mode, run), json.dumps({
        "day": _indy_day(now), "done": done, "due": due.isoformat() if due else None,
        "started": started.isoformat() if started else None, "payload": payload or {}}))


def _when(raw) -> datetime | None:
    try:
        return datetime.fromisoformat(raw) if raw else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# What a run does when it ends
# ---------------------------------------------------------------------------

def after_failure(db: Session, run: str, now: datetime, mode: str, auto: bool = False,
                  payload: dict | None = None, max_retries: int = MAX_RETRIES) -> Plan:
    """A run ended with customers (or the whole report) missed. Saves the next retry when one is left.
    auto=True means this attempt was itself an automatic retry. Never raises."""
    if mode == "off":
        return Plan(alert=True)                  # nothing is sent in off mode, so nothing is retried
    try:
        db.rollback()
        done = load(db, run, mode, now).get("done", 0)
        if done < max_retries:
            due = now + RETRY_DELAY
            _save(db, run, mode, now, done, due, payload=payload)
            arm(run, due)
            # The quiet middle attempt (an automatic retry with another one still to come) sends no alert
            return Plan(retry_at=due, alert=not (auto and done >= 1))
        _save(db, run, mode, now, done, None, payload=payload)
        return Plan(final=True)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Could not save a retry for {run}: {e}")
        return Plan(alert=True)


def after_success(db: Session, run: str, now: datetime, mode: str) -> None:
    """A run finished with nobody missed: any retry still waiting has nothing left to do. Never raises."""
    if mode == "off":
        return
    try:
        data = load(db, run, mode, now)
        if data.get("due"):
            _save(db, run, mode, now, data.get("done", 0), None, payload=data.get("payload"))
            _disarm(run)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Could not clear the retry for {run}: {e}")


# ---------------------------------------------------------------------------
# The timer
# ---------------------------------------------------------------------------

def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def arm(run: str, run_at: datetime) -> None:
    """One-off APScheduler job at run_at (naive UTC). Without a running scheduler the saved record still
    covers it: the next startup picks it up."""
    if _scheduler is None:
        return
    try:
        _scheduler.add_job(fire, "date", args=[run], id=f"{PREFIX}{run}", replace_existing=True,
                           run_date=run_at.replace(tzinfo=timezone.utc), name=f"Email retry: {run}",
                           misfire_grace_time=3600)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Could not set the retry timer for {run}: {e}")


def _disarm(run: str) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(f"{PREFIX}{run}")
    except Exception:  # noqa: BLE001
        pass   # no timer was set


def begin(db: Session, run: str, now: datetime, mode: str) -> tuple[str, dict]:
    """Claim a due retry. ('go', record) starts it; ('wait', record) means look again in a few minutes;
    ('none', {}) means nothing is due (not set, not yet due, already running, or from an earlier day)."""
    data = load(db, run, mode, now)
    due = _when(data.get("due"))
    if not due or due > now:
        return "none", {}
    started = _when(data.get("started"))
    if started and now - started < IN_PROGRESS:
        return "none", {}
    if run == "weekly" and _weekly_in_progress(db, mode, now):
        return "wait", data
    done = data.get("done", 0) + 1
    _save(db, run, mode, now, done, due, started=now, payload=data.get("payload"))
    data.update(done=done)
    return "go", data


def _weekly_in_progress(db: Session, mode: str, now: datetime) -> bool:
    """Another Thursday run began in the last 15 minutes and has not finished today."""
    from backend.emails import runner
    started_key, done_key = runner._weekly_keys(runner.state_mode(mode))
    if runner._get_setting(db, done_key) == _indy_day(now):
        return False
    started = _when(runner._get_setting(db, started_key))
    return bool(started and now - started < IN_PROGRESS)


def fire(run: str, now: datetime | None = None, mode: str | None = None, session_factory=None) -> dict:
    """The one-off job: run the failed job again, only if its saved retry is due."""
    from backend import activity
    from backend.emails.config import email_mode
    mode = mode or email_mode()
    if mode == "off":
        return {"ran": False}
    now = now or datetime.utcnow()
    if session_factory is None:
        from backend.database import SessionLocal as session_factory
    db = session_factory()
    try:
        status, data = begin(db, run, now, mode)
        if status == "wait":
            arm(run, now + RESUME_DELAY)
        if status != "go":
            return {"ran": False}
        logger.warning(f"Trying {run} again automatically (retry {data.get('done')})")
        with activity.run("job", "scheduler", f"Email retry: {run}"):
            return {"ran": True, "result": _run_again(db, run, data, now, mode)}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Automatic retry of {run} failed: {e}")   # the run itself already told Aaron
        return {"ran": True, "error": str(e)}
    finally:
        db.close()


def _run_again(db: Session, run: str, data: dict, now: datetime, mode: str):
    if run in EMAIL_RUNS:
        from backend.emails import runner
        return getattr(runner, EMAIL_RUNS[run])(db, now=now, mode=mode, auto_retry=True)
    payload = data.get("payload") or {}
    if run.startswith("weather_") and payload:
        from backend.services import weather_scheduler as WS
        return WS.run_check(payload["name"], tuple(payload["days"]), bool(payload["bamwx"]), report=True,
                            retry_key=run, auto_retry=True)
    return None


def resume(db: Session, now: datetime | None = None, mode: str | None = None) -> list[tuple[str, datetime]]:
    """On startup: a retry saved earlier today is set up again, and one that came due while the app was
    down runs a few minutes from now. Anything from an earlier day is dropped."""
    from backend.models.settings import SystemSettings
    from backend.emails.config import email_mode
    mode = mode or email_mode()
    if mode == "off":
        return []
    now = now or datetime.utcnow()
    prefix = f"{PREFIX}{_state_mode(mode)}_"
    out = []
    for row in db.query(SystemSettings).filter(SystemSettings.key.like(prefix + "%")).all():
        run = row.key[len(prefix):]
        data = load(db, run, mode, now)
        due = _when(data.get("due"))
        if not due:
            continue
        run_at = max(due, now + RESUME_DELAY)
        arm(run, run_at)
        out.append((run, run_at))
    return out
