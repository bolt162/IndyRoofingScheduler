"""
Court-admissible note generation — LOCAL ONLY.
Notes are generated and stored in the local database.
They are NEVER pushed to JobNimbus until the Phase 4 toggle is enabled.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models.note_log import NoteLog
from backend.models.job import Job
from backend.models.schedule import SchedulePlan


def _timestamp() -> str:
    return datetime.now().strftime("%B %d %Y %I:%M%p")


def generate_scheduling_note(db: Session, job: Job, plan: SchedulePlan | None = None, pm_name: str = "") -> NoteLog:
    """Generate a scheduling decision note for a job."""
    days_in_queue = 0
    if job.date_entered:
        days_in_queue = (datetime.utcnow() - job.date_entered).days

    parts = [
        f"[SCHEDULER SYSTEM -- {_timestamp()}]",
        f"Job selected for scheduling on {job.date_scheduled or 'TBD'}.",
        f"Scoring factors: {days_in_queue} days in queue,",
        f"{job.payment_type or 'unknown'} payment type,",
        f"{'single' if not job.secondary_trades else 'multi'} trade {job.primary_trade or 'unknown'},",
        f"{job.material_type or 'unknown'} material.",
    ]

    if job.must_build:
        parts.append(f"Must-Build anchor: Yes (deadline: {job.must_build_deadline}).")
    else:
        parts.append("Must-Build anchor: No.")

    if pm_name:
        parts.append(f"Assigned PM: {pm_name}.")

    parts.append(f"Duration: {job.duration_days} day{'s' if job.duration_days > 1 else ''} {'confirmed' if job.duration_confirmed else 'unconfirmed'}.")
    parts.append("Note generated automatically by Indy Roof Scheduling System.")

    note_text = " ".join(parts)

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="scheduling_decision",
        note_text=note_text,
        pushed_to_jn=False,
    )
    db.add(note)
    db.commit()
    return note


def generate_not_built_note(db: Session, job: Job, reason: str, detail: str = "") -> NoteLog:
    """Generate a Not Built note."""
    note_text = (
        f"[SCHEDULER SYSTEM -- {_timestamp()}] "
        f"Job returned to scheduling queue. Reason: {reason}."
    )
    if detail:
        note_text += f" Detail: {detail}."
    note_text += (
        f" Rescheduled count: {job.rescheduled_count}."
        " Note generated automatically by Indy Roof Scheduling System."
    )

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="not_built",
        note_text=note_text,
        pushed_to_jn=False,
    )
    db.add(note)
    db.commit()
    return note


def generate_secondary_trade_alert(db: Session, job: Job, days_since_primary: int) -> NoteLog:
    """Generate a secondary trade alert note."""
    remaining = [t for t in (job.secondary_trades or [])
                 if (job.secondary_trades_status or {}).get(t) != "complete"]
    note_text = (
        f"[SCHEDULER SYSTEM -- {_timestamp()}] "
        f"Primary trade ({job.primary_trade}) completed. "
        f"Secondary trades remaining: {', '.join(remaining) if remaining else 'none'}. "
        f"Days since primary completion: {days_since_primary}. "
        "Note generated automatically by Indy Roof Scheduling System."
    )

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="secondary_trade_alert",
        note_text=note_text,
        pushed_to_jn=False,
    )
    db.add(note)
    db.commit()
    return note


def generate_weather_rollback_note(db: Session, job: Job, weather_detail: str = "") -> NoteLog:
    """Generate a weather rollback note."""
    note_text = (
        f"[SCHEDULER SYSTEM -- {_timestamp()}] "
        f"Scheduled build removed due to weather conditions. "
        f"Forecast detail: {weather_detail or 'conditions did not meet material thresholds'}. "
        f"Job returned to scheduling queue with elevated priority. "
        "Note generated automatically by Indy Roof Scheduling System."
    )

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="weather_rollback",
        note_text=note_text,
        pushed_to_jn=False,
    )
    db.add(note)
    db.commit()
    return note


def generate_standalone_rule_note(db: Session, job: Job, option: str) -> NoteLog:
    """Generate a standalone rule note."""
    option_desc = "Saturday Build" if option == "saturday_build" else f"Sales Rep Managed ({job.sales_rep or 'TBD'})"
    note_text = (
        f"[SCHEDULER SYSTEM -- {_timestamp()}] "
        f"Standalone Rule triggered. No viable cluster partners within 40 miles. "
        f"Option selected: {option_desc}. "
        f"Payment type: {job.payment_type or 'unknown'}. "
        f"Days in queue: {(datetime.utcnow() - job.date_entered).days if job.date_entered else 'unknown'}. "
        "Note generated automatically by Indy Roof Scheduling System."
    )

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="standalone_rule",
        note_text=note_text,
        pushed_to_jn=False,
    )
    db.add(note)
    db.commit()
    return note


def generate_scheduling_notes(db: Session, plan: SchedulePlan) -> list[NoteLog]:
    """Generate scheduling notes for all jobs in a confirmed plan."""
    notes = []
    for job_id in plan.job_ids:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            note = generate_scheduling_note(db, job, plan)
            notes.append(note)
    return notes


def get_pending_notes(db: Session) -> list[NoteLog]:
    """Get all notes not yet pushed to JN."""
    return db.query(NoteLog).filter(NoteLog.pushed_to_jn == False).order_by(NoteLog.created_at.desc()).all()
