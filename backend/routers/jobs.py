from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.job import Job, JobBucket
from backend.models.note_log import NoteLog
from backend.schemas.job import JobResponse, JobCreate, JobUpdate, NotBuiltRequest
from backend.services.jobnimbus import sync_jobs_from_jn, _classify_duration_tier
from backend.services.geocoding import geocode_address

router = APIRouter()


def _enrich_with_latest_note(job: Job, db: Session) -> dict:
    """Add latest_system_note to job response."""
    job_dict = JobResponse.model_validate(job).model_dump()
    latest = db.query(NoteLog).filter(
        NoteLog.job_id == job.id
    ).order_by(NoteLog.created_at.desc()).first()
    job_dict["latest_system_note"] = latest.note_text if latest else None
    return job_dict


@router.post("/sync")
def sync_from_jn(db: Session = Depends(get_db)):
    """Trigger a manual JN sync."""
    result = sync_jobs_from_jn(db)
    return result


@router.post("/")
def create_job(data: JobCreate, db: Session = Depends(get_db)):
    """Manually create a new job (spec §11 Phase 1: manual job entry)."""
    from datetime import datetime

    # Classify duration tier from material + square footage
    tier, dur_confirmed, crew_flag = _classify_duration_tier(
        data.material_type, data.square_footage
    )

    # Determine initial bucket: low slope goes to pending_confirmation (spec §4.2)
    bucket = "to_schedule"
    if tier == "low_slope":
        bucket = "pending_confirmation"

    # Geocode address
    lat, lng = None, None
    coords = geocode_address(data.address)
    if coords:
        lat, lng = coords

    job = Job(
        customer_name=data.customer_name,
        address=data.address,
        latitude=lat,
        longitude=lng,
        job_type=data.job_type,
        payment_type=data.payment_type,
        primary_trade=data.primary_trade,
        secondary_trades=data.secondary_trades or [],
        material_type=data.material_type,
        square_footage=data.square_footage,
        sales_rep=data.sales_rep,
        duration_days=data.duration_days,
        duration_confirmed=dur_confirmed,
        duration_tier=tier,
        crew_requirement_flag=crew_flag,
        bucket=bucket,
        jn_notes_raw=data.notes or "",
        date_entered=datetime.utcnow(),
        jn_job_id=None,  # Not linked to JN
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _enrich_with_latest_note(job, db)


@router.get("/")
def list_jobs(bucket: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Job)
    if bucket:
        query = query.filter(Job.bucket == bucket)
    jobs = query.order_by(Job.score.desc()).all()
    return [_enrich_with_latest_note(j, db) for j in jobs]


@router.get("/buckets")
def get_bucket_counts(db: Session = Depends(get_db)):
    counts = {}
    for b in JobBucket:
        counts[b.value] = db.query(Job).filter(Job.bucket == b.value).count()
    return counts


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _enrich_with_latest_note(job, db)


@router.patch("/{job_id}")
def update_job(job_id: int, update: JobUpdate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    old_bucket = job.bucket
    old_date = str(job.date_scheduled) if job.date_scheduled else None
    update_data = update.model_dump(exclude_unset=True)

    # Handle 'notes' field mapping to jn_notes_raw
    if "notes" in update_data:
        job.jn_notes_raw = update_data.pop("notes") or ""

    for field, value in update_data.items():
        setattr(job, field, value)

    # Re-classify duration tier when material or square footage changes
    if "material_type" in update_data or "square_footage" in update_data:
        tier, dur_confirmed, crew_flag = _classify_duration_tier(
            job.material_type, job.square_footage
        )
        if not job.duration_confirmed:
            job.duration_tier = tier
            job.duration_confirmed = dur_confirmed
        job.crew_requirement_flag = crew_flag

    # Re-geocode when address changes
    if "address" in update_data:
        coords = geocode_address(job.address)
        if coords:
            job.latitude, job.longitude = coords

    db.commit()
    db.refresh(job)

    # Note 1: Generate scheduling decision note when:
    # - Job first moves to scheduled (new scheduling)
    # - OR date_scheduled changes on an already-scheduled job (rescheduled to different day)
    new_date = str(job.date_scheduled) if job.date_scheduled else None
    if job.bucket == "scheduled":
        if old_bucket != "scheduled" or old_date != new_date:
            from backend.services.notes import generate_scheduling_note
            generate_scheduling_note(db, job)

    return _enrich_with_latest_note(job, db)


@router.post("/{job_id}/must-build")
def set_must_build(job_id: int, update: JobUpdate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.must_build = True
    job.must_build_deadline = update.must_build_deadline
    job.must_build_reason = update.must_build_reason
    db.commit()
    db.refresh(job)
    return _enrich_with_latest_note(job, db)


@router.post("/{job_id}/not-built")
def mark_not_built(job_id: int, request: NotBuiltRequest, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.bucket = JobBucket.NOT_BUILT.value
    job.not_built_reason = request.reason
    job.rescheduled_count += 1
    job.priority_bump += 5.0  # elevated priority on return to queue
    db.commit()

    # Note 2: Generate not-built note with reason
    from backend.services.notes import generate_not_built_note
    generate_not_built_note(db, job, request.reason, request.detail or "")

    # Move back to to_schedule
    job.bucket = JobBucket.TO_SCHEDULE.value
    db.commit()
    db.refresh(job)
    return _enrich_with_latest_note(job, db)


class StandaloneOptionRequest(BaseModel):
    option: str  # "saturday_build" or "sales_rep_managed"


@router.post("/{job_id}/standalone-option")
def set_standalone_option(job_id: int, request: StandaloneOptionRequest, db: Session = Depends(get_db)):
    """Set standalone rule option (Saturday Build or Sales Rep Managed) and generate note."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if request.option not in ("saturday_build", "sales_rep_managed"):
        raise HTTPException(status_code=400, detail="Invalid option")

    job.standalone_option = request.option
    db.commit()

    # Note 5: Generate standalone rule note
    from backend.services.notes import generate_standalone_rule_note
    generate_standalone_rule_note(db, job, request.option)

    db.refresh(job)
    return _enrich_with_latest_note(job, db)


@router.get("/{job_id}/notes")
def get_job_notes(job_id: int, db: Session = Depends(get_db)):
    """Get all system-generated notes for a job."""
    notes = db.query(NoteLog).filter(
        NoteLog.job_id == job_id
    ).order_by(NoteLog.created_at.desc()).all()
    return [
        {
            "id": n.id,
            "note_type": n.note_type,
            "note_text": n.note_text,
            "pushed_to_jn": n.pushed_to_jn,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notes
    ]
