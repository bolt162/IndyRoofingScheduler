"""
Secondary trade escalation service.

Client requirement: once primary trade (roofing) is complete, secondary trades
(gutters, siding, etc.) should finish within 7 days. If not done within 10 days,
escalate higher — because revenue ($5K+) is floating while waiting.

This service runs daily and:
1. Finds jobs in primary_complete or waiting_on_trades buckets
2. Checks days since primary_complete_date
3. Generates warning note at 7+ days (once per job)
4. Generates escalation note at 10+ days (once per job)
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.note_log import NoteLog
from backend.models.settings import SystemSettings
from backend.services.notes import generate_secondary_trade_alert


logger = logging.getLogger("secondary_trade_escalation")


def _get_threshold(db: Session, key: str, default: int) -> int:
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    try:
        return int(setting.value) if setting and setting.value else default
    except (ValueError, TypeError):
        return default


def _has_alert_for_level(db: Session, job_id: int, level: str) -> bool:
    """
    Check if we already generated an alert at this escalation level for this job.
    Prevents duplicate notes on every daily run.
    """
    # Look for existing secondary_trade_alert notes. For escalated-level detection,
    # we check whether the note_text contains the ESCALATION banner.
    notes = db.query(NoteLog).filter(
        NoteLog.job_id == job_id,
        NoteLog.note_type == "secondary_trade_alert",
    ).all()

    for n in notes:
        has_escalation_banner = "SECONDARY TRADE ESCALATION" in (n.note_text or "")
        if level == "escalated" and has_escalation_banner:
            return True
        if level == "warning" and not has_escalation_banner:
            return True
    return False


def check_secondary_trade_aging(db: Session | None = None) -> dict:
    """
    Daily check for aging secondary trades.
    Generates warning and escalated notes as needed.
    Returns summary stats for logging.
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        warn_days = _get_threshold(db, "secondary_aging_yellow_days", 7)
        esc_days = _get_threshold(db, "secondary_aging_red_days", 10)

        # Find all jobs in buckets that have secondary trades pending
        target_buckets = [
            JobBucket.PRIMARY_COMPLETE.value,
            JobBucket.WAITING_ON_TRADES.value,
        ]
        candidate_jobs = db.query(Job).filter(
            Job.bucket.in_(target_buckets),
            Job.primary_complete_date.isnot(None),
        ).all()

        stats = {
            "checked": 0,
            "warnings_generated": 0,
            "escalations_generated": 0,
            "skipped_all_complete": 0,
        }

        for job in candidate_jobs:
            stats["checked"] += 1
            secondary_trades = job.secondary_trades or []
            if not secondary_trades:
                continue

            status_map = job.secondary_trades_status or {}
            open_trades = [t for t in secondary_trades if status_map.get(t) != "complete"]

            if not open_trades:
                # All complete — no alert needed
                stats["skipped_all_complete"] += 1
                continue

            days_since = (datetime.utcnow() - job.primary_complete_date).days

            if days_since >= esc_days:
                # Escalated level
                if not _has_alert_for_level(db, job.id, "escalated"):
                    generate_secondary_trade_alert(
                        db, job, days_since, escalation_level="escalated"
                    )
                    stats["escalations_generated"] += 1
                    logger.warning(
                        f"ESCALATION: {job.customer_name} (ID {job.id}) — "
                        f"{days_since}d since primary, open: {open_trades}"
                    )
            elif days_since >= warn_days:
                # Warning level
                if not _has_alert_for_level(db, job.id, "warning"):
                    generate_secondary_trade_alert(
                        db, job, days_since, escalation_level="warning"
                    )
                    stats["warnings_generated"] += 1
                    logger.info(
                        f"Warning: {job.customer_name} (ID {job.id}) — "
                        f"{days_since}d since primary, open: {open_trades}"
                    )

        return stats
    finally:
        if owns_session:
            db.close()


def run_daily_escalation_check():
    """Scheduled entry point for daily APScheduler job."""
    logger.info("Running daily secondary trade escalation check...")
    try:
        stats = check_secondary_trade_aging()
        logger.info(
            f"Secondary trade escalation check complete: "
            f"checked={stats['checked']}, "
            f"warnings={stats['warnings_generated']}, "
            f"escalations={stats['escalations_generated']}, "
            f"all_complete={stats['skipped_all_complete']}"
        )
    except Exception as e:
        logger.error(f"Secondary trade escalation check failed: {e}")
