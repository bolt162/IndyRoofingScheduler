from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.auth import ClerkUser, get_approved_user

router = APIRouter()


@router.get("/check/{job_id}")
def check_weather_for_job_endpoint(
    job_id: int, target_date: str | None = None, db: Session = Depends(get_db)
):
    from backend.services.weather import check_weather_for_job
    return check_weather_for_job(db, job_id, target_date)


@router.post("/check-all-scheduled")
def check_all_scheduled(db: Session = Depends(get_db)):
    """Check weather for all scheduled jobs. Auto-rollback do_not_build jobs."""
    from backend.services.weather import check_all_scheduled_jobs
    return check_all_scheduled_jobs(db)


class WeatherDecisionRequest(BaseModel):
    action: str  # "include" or "exclude"


@router.post("/{job_id}/decision")
def weather_decision(
    job_id: int, request: WeatherDecisionRequest, db: Session = Depends(get_db),
    user: ClerkUser = Depends(get_approved_user),
):
    """
    Scheduler Decision — confirm or exclude a marginal weather job (spec §6.3 line 265).
    "include" keeps the job scheduled. "exclude" is Not Built for weather: it takes the booking off
    JobNimbus's calendar and tells the customer, exactly like the Not Built button.
    """
    from backend.services.weather import handle_scheduler_decision
    if request.action not in ("include", "exclude"):
        raise HTTPException(status_code=400, detail="Action must be 'include' or 'exclude'")
    if request.action == "exclude":
        from backend.models.job import Job
        from backend.routers.jobs import _person, not_built
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        detail = job.weather_detail or "marginal conditions"
        job.weather_status = None  # decided; the flag shouldn't follow it back into the queue
        result = not_built(db, job, "Weather Pre-Build", detail, _person(db, user))
        return {"action": "excluded", "job_id": job.id, "jobnimbus": result}
    return handle_scheduler_decision(db, job_id, request.action)


@router.post("/{job_id}/bamwx-check")
def force_bamwx_check(
    job_id: int, target_date: str | None = None, db: Session = Depends(get_db)
):
    """
    Force a Clarity Wx (BamWx) check on a specific job.
    Scheduler override per spec §6.2 line 254.
    """
    from backend.services.weather import check_weather_for_job
    from backend.services.claritywx import is_configured
    if not is_configured():
        raise HTTPException(status_code=400, detail="BamWx/Clarity Wx not configured")
    return check_weather_for_job(db, job_id, target_date, force_bamwx=True)


@router.get("/provider-status")
def weather_provider_status():
    """Check which weather provider is active and if Clarity Wx is connected."""
    from backend.services.claritywx import is_configured, get_utilization
    if is_configured():
        usage = get_utilization()
        return {
            "provider": "claritywx",
            "connected": usage is not None,
            "usage": usage,
        }
    return {"provider": "openmeteo", "connected": True, "usage": None}
