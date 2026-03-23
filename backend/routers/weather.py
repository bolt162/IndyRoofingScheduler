from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db

router = APIRouter()


@router.get("/check/{job_id}")
def check_weather_for_job(job_id: int, target_date: str | None = None, db: Session = Depends(get_db)):
    from backend.services.weather import check_weather_for_job
    return check_weather_for_job(db, job_id, target_date)


@router.post("/check-all-scheduled")
def check_all_scheduled(db: Session = Depends(get_db)):
    from backend.services.weather import check_all_scheduled_jobs
    return check_all_scheduled_jobs(db)
