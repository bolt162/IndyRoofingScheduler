"""
Which email (if any) a job gets. Pure decision logic: no database, no sending.

Weekly (Thursday 10:00 AM) priority, per the handoff spec 4.4:
  1. reschedule track            -> Front of the line
  2. 3 or fewer ahead, never rescheduled, not yet sent -> Getting close
  3. office turned on weather slowdown this week       -> Weather slowdown
  4. next email in the trade's sequence (weeks 1-8, then rotation)
A job that never got a Welcome (e.g. it was already queued at launch) gets the Welcome first.
"""
from dataclasses import dataclass
from datetime import datetime, date, timedelta

from backend.emails import compose as K
from backend.emails.compose import EmailContext
from backend.models.email import EmailState

TRADE_TO_TRACK = {
    "roofing": "roof", "siding": "siding", "gutters": "gutters",
    "roofing_repair": "roof_repair", "siding_repair": "siding_repair",
}

QUEUE_BUCKET = "to_schedule"
QUEUE_JN_STATUSES = {"Schedule Job", "Schedule Production"}
DONE_BUCKETS = {"other_trades", "primary_completed", "completed", "archived"}

# A counted email in the last 6 days means "already emailed this week"
WEEK_WINDOW = timedelta(days=6)


@dataclass
class Decision:
    template: str | None            # None = send nothing
    reason: str = ""
    rotation_index: int = 0
    internal_alert: bool = False    # also send the PM/rep alert (second reschedule)


def new_state(job_id: int, mode: str = "live") -> EmailState:
    """EmailState with every default set explicitly (SQLAlchemy only applies defaults on flush)."""
    return EmailState(
        job_id=job_id, mode=mode, scheduled_seen_at=None, scheduled_email_sent=False,
        long_wait_alert_week=None, welcome_sent=False, sequence_week=0, rotation_index=0,
        getting_close_sent=False, last_jobs_ahead=None, last_counted_email_at=None,
        reschedule_track=False, reschedule_count_seen=0, original_date=None,
        reschedule_pending_since=None, suppressed=False, suppressed_reason=None,
        entered_queue_at=None,
    )


def track_for(primary_trade: str | None) -> str | None:
    """Primary trade picks the track. Windows, paint, interior, etc. get no queue emails."""
    return TRADE_TO_TRACK.get((primary_trade or "").lower())


def has_new_date(job, state: EmailState, today: date) -> bool:
    """A rescheduled job has a new build date: it's scheduled again on a different, upcoming day."""
    if job.bucket != "scheduled" or not job.date_scheduled:
        return False
    if job.date_scheduled < today:
        return False
    return state.original_date is None or job.date_scheduled != state.original_date


def in_queue(job, state: EmailState, today: date) -> bool:
    if job.bucket in DONE_BUCKETS:
        return False
    if job.bucket == QUEUE_BUCKET or (job.jn_status or "") in QUEUE_JN_STATUSES:
        return True
    # Rescheduled with no new date yet: still waiting even if JN still shows the old status
    return bool(state.reschedule_track) and not has_new_date(job, state, today)


def _gate(ctx: EmailContext, state: EmailState) -> str | None:
    """Reasons a customer can never be emailed. Returns a skip reason or None."""
    if state.suppressed:
        return f"suppressed ({state.suppressed_reason or 'manual'})"
    if ctx.is_commercial is None:
        return "commercial/residential unknown"
    if ctx.is_commercial:
        return "commercial"
    if not ctx.customer_email:
        return "no customer email"
    if ctx.contact_mismatch:
        return f"main contact on the job is {ctx.contact_mismatch}, not the customer"
    return None


def weekly_decision(ctx: EmailContext, state: EmailState, job, now: datetime,
                    weather_on: bool = False) -> Decision:
    reason = _gate(ctx, state)
    if reason:
        return Decision(None, reason)
    if not in_queue(job, state, now.date()):
        return Decision(None, "not in queue")
    if state.last_counted_email_at and now - state.last_counted_email_at < WEEK_WINDOW:
        return Decision(None, "already emailed this week")

    if not state.welcome_sent:
        return Decision(K.WELCOME, "welcome (not yet sent)")
    if state.reschedule_track:
        return Decision(K.FRONT_OF_LINE, "reschedule track", rotation_index=state.rotation_index)
    if K.is_repair(ctx.track):
        # Repairs: welcome, then a weekly check-in with a home care tip
        if weather_on:
            return Decision(K.WEATHER, "weather slowdown on")
        return Decision(K.ROTATION, "repair check-in", rotation_index=state.rotation_index)
    if ctx.jobs_ahead <= 3 and not state.getting_close_sent and ctx.rescheduled_count == 0:
        return Decision(K.GETTING_CLOSE, f"{ctx.jobs_ahead} ahead")
    if weather_on:
        return Decision(K.WEATHER, "weather slowdown on")
    if state.sequence_week < 8:
        return Decision(f"week_{state.sequence_week + 1}", "sequence")
    return Decision(K.ROTATION, "rotation", rotation_index=state.rotation_index)


def welcome_decision(ctx: EmailContext, state: EmailState, job, now: datetime) -> Decision:
    """Daily check for jobs that just entered the queue."""
    reason = _gate(ctx, state)
    if reason:
        return Decision(None, reason)
    if state.welcome_sent:
        return Decision(None, "welcome already sent")
    if not in_queue(job, state, now.date()):
        return Decision(None, "not in queue")
    return Decision(K.WELCOME, "entered queue")


def note_reschedule(state: EmailState, job, now: datetime) -> bool:
    """
    Call whenever a job's rescheduled_count may have gone up (Not Built, weather rollback).
    Records the date it was set for and starts the same-day wait. Returns True if it was new.
    """
    count = job.rescheduled_count or 0
    if count <= (state.reschedule_count_seen or 0):
        return False
    state.reschedule_count_seen = count
    if job.date_scheduled:
        state.original_date = job.date_scheduled
    state.reschedule_pending_since = now
    return True


def reschedule_decision(ctx: EmailContext, state: EmailState, job, now: datetime) -> Decision:
    """
    End-of-day check for a pending reschedule.
      new date already set  -> no customer email (scheduling confirmation covers it)
      first reschedule      -> Reschedule email, move to reschedule track
      second or later       -> Second reschedule email + internal alert to PM and rep
    """
    if not state.reschedule_pending_since:
        return Decision(None, "no pending reschedule")
    second = (job.rescheduled_count or 0) >= 2
    if has_new_date(job, state, now.date()):
        # The PM/rep alert still goes out on a second reschedule
        return Decision(None, "new date set", internal_alert=second)
    reason = _gate(ctx, state)
    if reason:
        return Decision(None, reason, internal_alert=second)
    if second:
        return Decision(K.SECOND_RESCHEDULE, "second reschedule", internal_alert=True)
    return Decision(K.RESCHEDULE, "first reschedule")


def apply_sent(state: EmailState, decision: Decision, ctx: EmailContext, now: datetime) -> None:
    """Advance the job's email state after a customer email went out (or would have, in a dry run)."""
    t = decision.template
    if t in (K.RESCHEDULE, K.SECOND_RESCHEDULE):
        state.reschedule_track = True
        state.reschedule_pending_since = None
        return  # reschedule emails don't count toward the weekly limit

    state.last_counted_email_at = now
    state.last_jobs_ahead = ctx.jobs_ahead
    if t == K.WELCOME:
        state.welcome_sent = True
    elif t == K.GETTING_CLOSE:
        state.getting_close_sent = True
    elif t in (K.ROTATION, K.FRONT_OF_LINE):
        state.rotation_index = (state.rotation_index or 0) + 1
    elif t and t.startswith("week_"):
        state.sequence_week = int(t.split("_")[1])


def clear_reschedule_if_dated(state: EmailState, job, today: date) -> None:
    """Leave the reschedule track once a new date is set."""
    if state.reschedule_track and has_new_date(job, state, today):
        state.reschedule_track = False
        state.reschedule_pending_since = None
