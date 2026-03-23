from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.job import Job, JobBucket
from backend.schemas.job import JobResponse, JobUpdate, NotBuiltRequest

router = APIRouter()


@router.get("/", response_model=list[JobResponse])
def list_jobs(bucket: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Job)
    if bucket:
        query = query.filter(Job.bucket == bucket)
    return query.order_by(Job.score.desc()).all()


@router.get("/buckets")
def get_bucket_counts(db: Session = Depends(get_db)):
    counts = {}
    for b in JobBucket:
        counts[b.value] = db.query(Job).filter(Job.bucket == b.value).count()
    return counts


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(job_id: int, update: JobUpdate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/must-build", response_model=JobResponse)
def set_must_build(job_id: int, update: JobUpdate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.must_build = True
    job.must_build_deadline = update.must_build_deadline
    job.must_build_reason = update.must_build_reason
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/not-built", response_model=JobResponse)
def mark_not_built(job_id: int, request: NotBuiltRequest, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.bucket = JobBucket.NOT_BUILT.value
    job.not_built_reason = request.reason
    job.rescheduled_count += 1
    job.priority_bump += 5.0  # elevated priority on return to queue
    db.commit()
    # Move back to to_schedule
    job.bucket = JobBucket.TO_SCHEDULE.value
    db.commit()
    db.refresh(job)
    return job
