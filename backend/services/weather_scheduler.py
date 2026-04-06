"""
Automated weather checks — APScheduler jobs per spec §6.2, §6.4.

Three scheduled checks:
1. Morning check (default 6:00 AM) — all scheduled jobs for today + tomorrow
2. Night-before check (default 8:00 PM) — all jobs scheduled for tomorrow (final authority)
3. 5am spot check — last-minute sanity on today's builds

All checks use the dual-provider weather service (Clarity Wx if configured, else Open-Meteo).
Results are stored in the weather_alerts table and available via GET /weather/alerts.
"""
import logging
from datetime import date, timedelta

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.settings import SystemSettings
from backend.services.weather import check_weather_for_job, _auto_rollback_job

logger = logging.getLogger("weather_scheduler")


def _get_setting_value(db, key: str, default: str = "") -> str:
    s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return s.value if s else default


def morning_weather_check():
    """
    Morning check (spec §6.2 line 252): "Runs every morning automatically on all scheduled jobs."
    Checks all jobs scheduled for today and tomorrow.
    Auto-rollback any "do_not_build" results.
    """
    logger.info("Running morning weather check...")
    db = SessionLocal()
    try:
        today = date.today()
        tomorrow = today + timedelta(days=1)

        jobs = db.query(Job).filter(
            Job.bucket == JobBucket.SCHEDULED.value,
            Job.date_scheduled.in_([today, tomorrow]),
        ).all()

        checked = 0
        rolled_back = 0
        for job in jobs:
            target = str(job.date_scheduled) if job.date_scheduled else None
            result = check_weather_for_job(db, job.id, target)
            checked += 1

            if result.get("status") == "do_not_build":
                _auto_rollback_job(db, job, result.get("detail", ""))
                rolled_back += 1
                logger.warning(
                    f"Auto-rollback: {job.customer_name} (ID {job.id}) — {result.get('detail')}"
                )

        logger.info(f"Morning check complete: {checked} checked, {rolled_back} rolled back")
    except Exception as e:
        logger.error(f"Morning weather check failed: {e}")
    finally:
        db.close()


def night_before_check():
    """
    Night-before check (spec §6.4 lines 267-269):
    "Every evening at a configurable time, the system automatically runs
    all next-day builds through BamWx."
    Uses Clarity Wx (if configured) as final authority.
    """
    logger.info("Running night-before weather check...")
    db = SessionLocal()
    try:
        tomorrow = date.today() + timedelta(days=1)

        jobs = db.query(Job).filter(
            Job.bucket == JobBucket.SCHEDULED.value,
            Job.date_scheduled == tomorrow,
        ).all()

        checked = 0
        rolled_back = 0
        for job in jobs:
            # Use force_bamwx=True to ensure Clarity Wx is used (final authority)
            result = check_weather_for_job(
                db, job.id, str(tomorrow), force_bamwx=True
            )
            checked += 1

            if result.get("status") == "do_not_build":
                _auto_rollback_job(db, job, result.get("detail", ""))
                rolled_back += 1
                logger.warning(
                    f"Night-before rollback: {job.customer_name} (ID {job.id}) — {result.get('detail')}"
                )
            elif result.get("status") == "scheduler_decision":
                logger.info(
                    f"Scheduler decision needed: {job.customer_name} (ID {job.id}) — {result.get('detail')}"
                )

        logger.info(f"Night-before check complete: {checked} checked, {rolled_back} rolled back")
    except Exception as e:
        logger.error(f"Night-before weather check failed: {e}")
    finally:
        db.close()


def five_am_spot_check():
    """
    5am spot check (spec §6.2 line 255):
    "5am morning-of spot check on all next-day builds as a final free sanity check."
    Checks all jobs scheduled for TODAY — last chance before crews go out.
    """
    logger.info("Running 5am spot check...")
    db = SessionLocal()
    try:
        today = date.today()

        jobs = db.query(Job).filter(
            Job.bucket == JobBucket.SCHEDULED.value,
            Job.date_scheduled == today,
        ).all()

        checked = 0
        rolled_back = 0
        changed = 0
        for job in jobs:
            old_status = job.weather_status
            result = check_weather_for_job(db, job.id, str(today))
            checked += 1

            new_status = result.get("status")

            # Track status changes (spec §6.2: "if conditions change, fires an alert")
            if old_status != new_status:
                changed += 1
                logger.info(
                    f"Weather changed for {job.customer_name}: {old_status} → {new_status}"
                )

            if new_status == "do_not_build":
                _auto_rollback_job(db, job, result.get("detail", ""))
                rolled_back += 1
                logger.warning(
                    f"5am rollback: {job.customer_name} (ID {job.id}) — {result.get('detail')}"
                )

        logger.info(
            f"5am spot check complete: {checked} checked, {changed} changed, {rolled_back} rolled back"
        )
    except Exception as e:
        logger.error(f"5am spot check failed: {e}")
    finally:
        db.close()
