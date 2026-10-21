"""
Automated weather checks — APScheduler jobs per spec §6.2, §6.4.

Three scheduled checks of builds booked in JobNimbus (their work order date):
1. Morning check (default 6:00 AM): builds today + tomorrow, free forecast (Open-Meteo)
2. Night-before check (default 8:00 PM): builds tomorrow, BAM Wx (Clarity Wx) for the address
3. 5am spot check: today's builds, BAM Wx for the address
BAM Wx is only for those two address checks; weekly looks use the free forecast (Aaron, 2026-10-21).

A do-not-build forecast flags the build (weather.flag_do_not_build) instead of pulling it in the
app alone; the scheduler moves it with Move or Not Built, which update JobNimbus and the customer.
Days are Indianapolis days (the server clock is UTC: at 8 PM here it's already tomorrow there).
"""
import logging
from datetime import timedelta

from backend.database import SessionLocal
from backend.models.job import Job, JobBucket
from backend.models.settings import SystemSettings
from backend.services.weather import build_date, check_weather_for_job, flag_do_not_build

logger = logging.getLogger("weather_scheduler")


def _get_setting_value(db, key: str, default: str = "") -> str:
    s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return s.value if s else default


def _today():
    from backend.services.no_build import local_today
    return local_today()


def _booked_on(db, days: set) -> list[Job]:
    return [j for j in db.query(Job).filter(Job.bucket == JobBucket.SCHEDULED.value).all() if build_date(j) in days]


def run_check(name: str, days_from_today: tuple[int, ...], bamwx: bool) -> dict:
    db = SessionLocal()
    checked = flagged = changed = 0
    try:
        today = _today()
        for job in _booked_on(db, {today + timedelta(days=n) for n in days_from_today}):
            old = job.weather_status
            result = check_weather_for_job(db, job.id, str(build_date(job)), force_bamwx=bamwx)
            checked += 1
            status = result.get("status")
            if old != status:
                changed += 1
                logger.info(f"{name}: weather changed for {job.customer_name}: {old} -> {status}")
            if status == "do_not_build":
                flag_do_not_build(db, job, result.get("detail", ""), name)
                flagged += 1
                logger.warning(f"{name}: don't build {job.customer_name} (ID {job.id}): {result.get('detail')}")
            elif status == "scheduler_decision":
                logger.info(f"{name}: scheduler decision for {job.customer_name} (ID {job.id}): {result.get('detail')}")
        logger.info(f"{name} complete: {checked} checked, {changed} changed, {flagged} flagged")
    except Exception as e:
        logger.error(f"{name} failed: {e}")
    finally:
        db.close()
    return {"checked": checked, "changed": changed, "flagged": flagged}


def morning_weather_check():
    """Builds today and tomorrow, free forecast (spec §6.2)."""
    return run_check("Morning weather check", (0, 1), bamwx=False)


def night_before_check():
    """Tomorrow's builds, BAM Wx for the address (spec §6.4, final authority)."""
    return run_check("Night-before weather check", (1,), bamwx=True)


def five_am_spot_check():
    """Today's builds, BAM Wx for the address: last look before crews go out (spec §6.2)."""
    return run_check("5am weather spot check", (0,), bamwx=True)
