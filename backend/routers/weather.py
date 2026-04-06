from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db

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
    job_id: int, request: WeatherDecisionRequest, db: Session = Depends(get_db)
):
    """
    Scheduler Decision — confirm or exclude a marginal weather job (spec §6.3 line 265).
    "include" keeps the job scheduled, "exclude" moves to Not Built.
    """
    from backend.services.weather import handle_scheduler_decision
    if request.action not in ("include", "exclude"):
        raise HTTPException(status_code=400, detail="Action must be 'include' or 'exclude'")
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
