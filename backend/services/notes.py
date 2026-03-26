"""
Court-admissible note generation — LOCAL ONLY.
Notes are generated and stored in the local database.
They are NEVER pushed to JobNimbus until the Phase 4 toggle is enabled.

Templates are loaded from SystemSettings and rendered with str.format().
Each NoteLog records the template_version (updated_at timestamp) for audit.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models.note_log import NoteLog
from backend.models.job import Job
from backend.models.schedule import SchedulePlan
from backend.models.settings import SystemSettings


# Fallback templates used when DB has no setting (e.g. first run before seed)
FALLBACK_TEMPLATES = {
    "note_template_scheduling": (
        "[SCHEDULER SYSTEM -- {timestamp}] Job selected for scheduling on {date_scheduled}. "
        "Scoring factors: {days_in_queue} days in queue, {payment_type} payment type, "
        "{trade_desc} trade {primary_trade}, {material_type} material. "
        "Must-Build anchor: {must_build}. {pm_line}"
        "Duration: {duration}. Note generated automatically by Indy Roof Scheduling System."
    ),
    "note_template_not_built": (
        "[SCHEDULER SYSTEM -- {timestamp}] Job returned to scheduling queue. "
        "Reason: {reason}. {detail_line}"
        "Rescheduled count: {rescheduled_count}. "
        "Note generated automatically by Indy Roof Scheduling System."
    ),
    "note_template_secondary_trade_alert": (
        "[SCHEDULER SYSTEM -- {timestamp}] Primary trade ({primary_trade}) completed. "
        "Secondary trades remaining: {remaining_trades}. "
        "Days since primary completion: {days_since_primary}. "
        "Note generated automatically by Indy Roof Scheduling System."
    ),
    "note_template_weather_rollback": (
        "[SCHEDULER SYSTEM -- {timestamp}] Scheduled build removed due to weather conditions. "
        "Forecast detail: {weather_detail}. "
        "Job returned to scheduling queue with elevated priority. "
        "Note generated automatically by Indy Roof Scheduling System."
    ),
    "note_template_standalone_rule": (
        "[SCHEDULER SYSTEM -- {timestamp}] Standalone Rule triggered. "
        "No viable cluster partners within 40 miles. "
        "Option selected: {option_desc}. Payment type: {payment_type}. "
        "Days in queue: {days_in_queue}. "
        "Note generated automatically by Indy Roof Scheduling System."
    ),
}


def _timestamp() -> str:
    return datetime.now().strftime("%B %d %Y %I:%M%p")


def _load_template(db: Session, key: str) -> tuple[str, datetime | None]:
    """Load a note template from settings. Returns (template_str, version_timestamp)."""
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if setting:
        return setting.value, setting.updated_at
    return FALLBACK_TEMPLATES.get(key, ""), None


def _render_note(db: Session, template_key: str, context: dict) -> tuple[str, datetime | None]:
    """Load template and render with context. Returns (rendered_text, template_version)."""
    template, version = _load_template(db, template_key)
    context.setdefault("timestamp", _timestamp())
    try:
        return template.format(**context), version
    except KeyError:
        # If user edited template with bad placeholders, fall back to default
        fallback = FALLBACK_TEMPLATES.get(template_key, "")
        return fallback.format(**context), None


def generate_scheduling_note(db: Session, job: Job, plan: SchedulePlan | None = None, pm_name: str = "") -> NoteLog:
    """Generate a scheduling decision note for a job."""
    days_in_queue = 0
    if job.date_entered:
        days_in_queue = (datetime.utcnow() - job.date_entered).days

    context = {
        "date_scheduled": job.date_scheduled or "TBD",
        "days_in_queue": days_in_queue,
        "payment_type": job.payment_type or "unknown",
        "trade_desc": "single" if not job.secondary_trades else "multi",
        "primary_trade": job.primary_trade or "unknown",
        "material_type": job.material_type or "unknown",
        "must_build": f"Yes (deadline: {job.must_build_deadline})" if job.must_build else "No",
        "pm_line": f"Assigned PM: {pm_name}. " if pm_name else "",
        "duration": f"{job.duration_days} day{'s' if job.duration_days > 1 else ''} {'confirmed' if job.duration_confirmed else 'unconfirmed'}",
    }

    note_text, template_version = _render_note(db, "note_template_scheduling", context)

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="scheduling_decision",
        note_text=note_text,
        pushed_to_jn=False,
        template_version=template_version,
    )
    db.add(note)
    db.commit()
    return note


def generate_not_built_note(db: Session, job: Job, reason: str, detail: str = "") -> NoteLog:
    """Generate a Not Built note."""
    context = {
        "reason": reason,
        "detail_line": f"Detail: {detail}. " if detail else "",
        "rescheduled_count": job.rescheduled_count,
    }

    note_text, template_version = _render_note(db, "note_template_not_built", context)

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="not_built",
        note_text=note_text,
        pushed_to_jn=False,
        template_version=template_version,
    )
    db.add(note)
    db.commit()
    return note


def generate_secondary_trade_alert(db: Session, job: Job, days_since_primary: int) -> NoteLog:
    """Generate a secondary trade alert note."""
    remaining = [t for t in (job.secondary_trades or [])
                 if (job.secondary_trades_status or {}).get(t) != "complete"]
    context = {
        "primary_trade": job.primary_trade,
        "remaining_trades": ", ".join(remaining) if remaining else "none",
        "days_since_primary": days_since_primary,
    }

    note_text, template_version = _render_note(db, "note_template_secondary_trade_alert", context)

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="secondary_trade_alert",
        note_text=note_text,
        pushed_to_jn=False,
        template_version=template_version,
    )
    db.add(note)
    db.commit()
    return note


def generate_weather_rollback_note(db: Session, job: Job, weather_detail: str = "") -> NoteLog:
    """Generate a weather rollback note."""
    context = {
        "weather_detail": weather_detail or "conditions did not meet material thresholds",
    }

    note_text, template_version = _render_note(db, "note_template_weather_rollback", context)

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="weather_rollback",
        note_text=note_text,
        pushed_to_jn=False,
        template_version=template_version,
    )
    db.add(note)
    db.commit()
    return note


def generate_standalone_rule_note(db: Session, job: Job, option: str) -> NoteLog:
    """Generate a standalone rule note."""
    context = {
        "option_desc": "Saturday Build" if option == "saturday_build" else f"Sales Rep Managed ({job.sales_rep or 'TBD'})",
        "payment_type": job.payment_type or "unknown",
        "days_in_queue": (datetime.utcnow() - job.date_entered).days if job.date_entered else "unknown",
    }

    note_text, template_version = _render_note(db, "note_template_standalone_rule", context)

    note = NoteLog(
        job_id=job.id,
        jn_job_id=job.jn_job_id,
        note_type="standalone_rule",
        note_text=note_text,
        pushed_to_jn=False,
        template_version=template_version,
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
