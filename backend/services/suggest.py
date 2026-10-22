"""
"Suggest builds" on the Weekly Plan: pencil in the rest of a week around what's already there.

Nothing here is a plan or a booking. Suggestions live in their own fields (suggested_*) until the
scheduler keeps one (it becomes a normal plan they can push) or dismisses it. Push to JobNimbus
never sees them.

How a week is filled, Monday to Friday, from tomorrow on:
  - Jobs planned here or booked in JobNimbus stay put; their crews and PMs count as busy those days
    (a 2-day build keeps its crew busy both days).
  - Full roofs only (Aaron, 2026-10-22): repairs, siding and gutters are placed by hand.
  - Waiting jobs (To Schedule / Not Built, no plan yet) go in order: must-build first, then the same
    score the Unassigned list sorts by. Jobs the ready check flagged or put on hold are skipped.
  - Each crew does its own trade, one build at a time, and the whole build fits inside Mon to Fri.
  - Skipped for a day: the customer's No-Build Dates, or a do-not-build forecast for that material.
  - PMs: the ones picked in the header (else every active PM), up to each one's daily max.
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from backend.models.job import Job
from backend.models.pm import PM, Crew

logger = logging.getLogger("suggest")

WAITING = ("to_schedule", "not_built")
BLOCKED_READY = ("flagged", "hold")
SUGGESTED_TRADES = ("roofing",)  # full roofs


def _is_test(name: str | None) -> bool:
    # The practice setup (test jobs "TEST ... (ignore)", "IRR Test Crew", test PM) must never be
    # suggested onto, or with, real work
    return "test" in (name or "").lower()


def week_days(week_start: date, today: date) -> list[date]:
    monday = week_start - timedelta(days=week_start.weekday())
    return [d for d in (monday + timedelta(days=i) for i in range(5)) if d > today]


def _trade_ok(crew: Crew, trade: str | None) -> bool:
    from backend.services.crew_matching import _trade_matches
    t = trade or ""
    return _trade_matches(crew, t) or (t.endswith("_repair") and _trade_matches(crew, t.removesuffix("_repair")))


def _span(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(max(1, days))]


def _days_for(job: Job, crew: Crew) -> int:
    from backend.services import build_days as bd
    sug = bd.suggestion(job, crew.name)
    return (sug or {}).get("days") or job.duration_days or 1


def clear(db: Session, week_start: date | None = None, job_ids: list[int] | None = None) -> int:
    """Dismiss suggestions: one week's, or just these jobs'."""
    q = db.query(Job).filter(Job.suggested_date.isnot(None))
    if job_ids is not None:
        q = q.filter(Job.id.in_(job_ids))
    if week_start is not None:
        monday = week_start - timedelta(days=week_start.weekday())
        q = q.filter(Job.suggested_date >= monday, Job.suggested_date < monday + timedelta(days=7))
    n = 0
    for job in q.all():
        clear_job(job)
        n += 1
    db.commit()
    return n


def clear_job(job: Job) -> None:
    job.suggested_date = job.suggested_crew_id = job.suggested_pm_id = job.suggested_days = None
    job.suggested_why = None


def keep(db: Session, job_ids: list[int], who: str) -> int:
    """The scheduler likes these: they become normal plans (still not sent to JobNimbus)."""
    n = 0
    for job in db.query(Job).filter(Job.id.in_(job_ids), Job.suggested_date.isnot(None)).all():
        if job.bucket not in WAITING or job.planned_date:
            clear_job(job)
            continue
        job.planned_date, job.planned_crew_id, job.planned_pm_id = (
            job.suggested_date, job.suggested_crew_id, job.suggested_pm_id)
        job.planned_days = None  # follows the work order's suggestion for that crew, like any plan
        job.planned_by, job.planned_at = who, datetime.utcnow()
        clear_job(job)
        n += 1
    db.commit()
    return n


class _Forecasts:
    """Do-not-build days by area and day, so one forecast serves every job nearby."""

    def __init__(self, db: Session):
        self.db = db
        self.cache: dict[tuple, dict | None] = {}

    def blocked(self, job: Job, day: date) -> str | None:
        if job.must_build or not (job.latitude and job.longitude):
            return None
        from backend.services.weather import check_material_thresholds, get_forecast
        key = (round(job.latitude, 1), round(job.longitude, 1), day)
        if key not in self.cache:
            try:
                self.cache[key] = get_forecast(job.latitude, job.longitude, day.isoformat())
            except Exception as e:  # noqa: BLE001  (no forecast never blocks a suggestion)
                logger.warning(f"Forecast failed for {key}: {e}")
                self.cache[key] = None
        forecast = self.cache[key]
        if not forecast:
            return None
        try:
            r = check_material_thresholds(self.db, job.material_type or "", forecast,
                                          primary_trade=job.primary_trade or "")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Weather check failed for job {job.id}: {e}")
            return None
        return r.get("detail") or "forecast" if r.get("status") == "do_not_build" else None


def suggest_week(db: Session, week_start: date, pm_ids: list[int] | None = None, today: date | None = None,
                 forecasts: _Forecasts | None = None) -> dict:
    from backend.services import no_build
    from backend.services.jn_booking import build_days, crew_for_names
    today = today or no_build.local_today()
    days = week_days(week_start, today)
    clear(db, week_start=week_start)
    if not days:
        return {"suggested": [], "reason": "No build days left in this week."}

    crews = sorted((c for c in db.query(Crew).filter(Crew.is_active.is_(True)).all() if not _is_test(c.name)),
                   key=lambda c: (c.rank or 999, c.name))
    pms = [p for p in db.query(PM).filter(PM.is_active.is_(True)).all()
           if (p.id in pm_ids if pm_ids else not _is_test(p.name))]
    if not crews:
        return {"suggested": [], "reason": "No active crews to suggest with."}
    if not pms:
        return {"suggested": [], "reason": "No PM to suggest with. Pick one in the header."}

    # What's already on the calendar
    busy: dict[int, set[date]] = {c.id: set() for c in crews}
    pm_load: dict[tuple[int, date], int] = {}
    pm_by_name = {p.name.lower(): p for p in db.query(PM).all()}
    for job in db.query(Job).filter(Job.planned_date.isnot(None)).all():
        crew = db.get(Crew, job.planned_crew_id) if job.planned_crew_id else None
        for d in _span(job.planned_date, build_days(job, crew)):
            if crew and crew.id in busy:
                busy[crew.id].add(d)
            if job.planned_pm_id:
                pm_load[(job.planned_pm_id, d)] = pm_load.get((job.planned_pm_id, d), 0) + 1
    for job in db.query(Job).filter(Job.bucket == "scheduled", Job.jn_start_date.isnot(None)).all():
        crew = crew_for_names(db, job.jn_crews)
        pm = next((p for n, p in pm_by_name.items() if job.jn_pm and job.jn_pm.lower().startswith(n)), None)
        for d in _span(job.jn_start_date, job.duration_days or 1):
            if crew and crew.id in busy:
                busy[crew.id].add(d)
            if pm:
                pm_load[(pm.id, d)] = pm_load.get((pm.id, d), 0) + 1

    # Not already suggested for another week (this week's were just cleared)
    waiting = [j for j in db.query(Job).filter(Job.bucket.in_(WAITING), Job.planned_date.is_(None),
                                               Job.suggested_date.is_(None),
                                               Job.primary_trade.in_(SUGGESTED_TRADES)).all()
               if j.ready_status not in BLOCKED_READY and not _is_test(j.customer_name)]
    waiting.sort(key=lambda j: (not j.must_build, -(j.score or 0), j.id))
    forecasts = forecasts or _Forecasts(db)
    last_day = days[0] - timedelta(days=days[0].weekday()) + timedelta(days=4)  # Friday

    placed: list[Job] = []
    for day in days:
        for crew in crews:
            if day in busy[crew.id]:
                continue
            for job in waiting:
                if job in placed or not _trade_ok(crew, job.primary_trade):
                    continue
                n = _days_for(job, crew)
                span = _span(day, n)
                if span[-1] > last_day or any(d in busy[crew.id] for d in span):
                    continue
                if no_build.job_conflict(job, day, n) or forecasts.blocked(job, day):
                    continue
                pm = min((p for p in pms if all(pm_load.get((p.id, d), 0) < (p.max_capacity or 5) for d in span)),
                         key=lambda p: (pm_load.get((p.id, day), 0) >= (p.baseline_capacity or 3),
                                        pm_load.get((p.id, day), 0), p.name), default=None)
                if not pm:
                    continue
                job.suggested_date, job.suggested_crew_id, job.suggested_pm_id = day, crew.id, pm.id
                job.suggested_days = n
                why = ["must build"] if job.must_build else []
                why.append(f"score {job.score:.0f}" if job.score else "oldest waiting")
                job.suggested_why = ", ".join(why)[:255]
                busy[crew.id].update(span)
                for d in span:
                    pm_load[(pm.id, d)] = pm_load.get((pm.id, d), 0) + 1
                placed.append(job)
                break
    db.commit()
    return {"suggested": [{"job_id": j.id, "customer_name": j.customer_name, "date": j.suggested_date.isoformat(),
                           "crew_id": j.suggested_crew_id, "pm_id": j.suggested_pm_id, "days": j.suggested_days}
                          for j in placed],
            "waiting": len(waiting) - len(placed)}
