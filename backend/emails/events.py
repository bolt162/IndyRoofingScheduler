"""
Record what happens to jobs so the email runner can act on it.

Called from the existing scheduler code paths:
  - after every JobNimbus sync   -> after_sync()      (queue entry, scheduled, finished)
  - Mark Not Built / weather rollback -> on_reschedule()

Everything here is wrapped by the callers so an email problem can never break a sync or
a button the office relies on. Nothing here sends email; it only records facts.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.emails import selector as S
from backend.models.email import EmailState, JobEvent

logger = logging.getLogger("emails.events")

MODES = ("test", "live")
DONE_BUCKETS = {"other_trades", "primary_completed", "completed"}


def states_for(db: Session, job_id: int) -> dict[str, EmailState]:
    """The job's test and live email state rows, created if missing."""
    rows = {r.mode: r for r in db.query(EmailState).filter(EmailState.job_id == job_id).all()}
    for mode in MODES:
        if mode not in rows:
            rows[mode] = S.new_state(job_id, mode)
            db.add(rows[mode])
    return rows


def _jn_time(value) -> datetime | None:
    if isinstance(value, (int, float)) and value > 0:
        return datetime.utcfromtimestamp(value)
    return None


def _in_queue(job) -> bool:
    return job.bucket == S.QUEUE_BUCKET or (job.jn_status or "") in S.QUEUE_JN_STATUSES


def after_sync(db: Session, observed: list[tuple], now: datetime | None = None) -> dict:
    """
    observed: (job, old_bucket, jn_data) for every job the sync touched. old_bucket is None
    for a job created by this sync. Returns counts for logging.
    """
    now = now or datetime.utcnow()
    counts = {"events": 0, "entered_queue": 0, "scheduled": 0}
    for job, old_bucket, jn_data in observed:
        if job.id is None:
            continue
        new_bucket = job.bucket
        if old_bucket != new_bucket:
            db.add(JobEvent(job_id=job.id, from_bucket=old_bucket, to_bucket=new_bucket,
                            primary_trade=job.primary_trade, created_at=now))
            counts["events"] += 1

        in_queue = _in_queue(job)
        just_scheduled = new_bucket == "scheduled" and old_bucket not in (None, "scheduled")
        if not in_queue and not just_scheduled:
            continue

        for state in states_for(db, job.id).values():
            if in_queue and state.entered_queue_at is None:
                # A job already in the queue when we first see it: JobNimbus's last status
                # change is when it got there. A job moving in during this sync: now.
                moved_in_now = old_bucket is not None and old_bucket != new_bucket
                state.entered_queue_at = now if moved_in_now else (
                    _jn_time((jn_data or {}).get("date_status_change")) or now)
                counts["entered_queue"] += 1
            if just_scheduled and not state.scheduled_email_sent and state.scheduled_seen_at is None:
                state.scheduled_seen_at = now
                counts["scheduled"] += 1
    db.commit()
    return counts


def on_reschedule(db: Session, job, now: datetime | None = None) -> None:
    """A scheduled build was pushed (Not Built or weather). Starts the same-day reschedule wait."""
    now = now or datetime.utcnow()
    for state in states_for(db, job.id).values():
        S.note_reschedule(state, job, now)
        # A new scheduled date later should earn a fresh look, but not a second fun email
        state.scheduled_seen_at = None if not state.scheduled_email_sent else state.scheduled_seen_at
    db.commit()


def safely(fn, *args, **kwargs):
    """Run an email hook without ever letting it break the caller."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Email hook {getattr(fn, '__name__', fn)} failed: {e}")
        try:
            args[0].rollback()
        except Exception:
            pass
        return None
