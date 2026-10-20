from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schedule import SchedulePlan
from backend.services.auth import ClerkUser, get_approved_user

router = APIRouter()


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    return db.query(SchedulePlan).order_by(SchedulePlan.plan_date.desc()).all()


@router.post("/confirm/{plan_id}")
def confirm_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if not plan:
        return {"error": "Plan not found"}
    plan.status = "confirmed"
    db.commit()
    # Generate notes locally (not pushed to JN)
    from backend.services.notes import generate_scheduling_notes
    notes = generate_scheduling_notes(db, plan)
    return {"status": "confirmed", "notes_generated": len(notes)}


# --- Push to JobNimbus: book the Weekly Plan's picks the way Greg does by hand ---

@router.get("/push-preview")
def push_preview(db: Session = Depends(get_db), user: ClerkUser = Depends(get_approved_user)):
    """Which planned jobs would be sent, and why the others won't. Reads nothing from JobNimbus."""
    from backend.services import jn_booking
    return {**jn_booking.preview(db), "can_book": can_book(db, user)}


BOOKING_ROLES = ("office", "ops", "owner")


def can_book(db: Session, user: ClerkUser) -> bool:
    """Booking texts customers, so only Greg, Nikka, Ross, owners and admins (not reps) can do it."""
    from backend.models.email import TeamContact
    from backend.services.auth import is_owner_or_admin
    if is_owner_or_admin(user):
        return True
    if not user.email:
        return False
    row = db.query(TeamContact).filter(TeamContact.email.ilike(user.email)).first()
    return bool(row and row.role in BOOKING_ROLES and getattr(row, "is_active", True) is not False)


class MoveRequest(BaseModel):
    job_id: int
    new_date: date
    reason: str = ""


@router.post("/move")
def move_booked_job(request: MoveRequest, db: Session = Depends(get_db),
                    user: ClerkUser = Depends(get_approved_user)):
    """Move a job booked in JobNimbus to a new day (off the calendar and booked again)."""
    from backend.models.job import Job
    from backend.routers.jobs import _person
    from backend.services import jn_booking
    if not can_book(db, user):
        raise HTTPException(status_code=403, detail="Only the office, operations or owners can move bookings in JobNimbus.")
    job = db.get(Job, request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if jn_booking.mode() == "off" or not jn_booking.allowed(job):
        raise HTTPException(status_code=409, detail="Sending to JobNimbus is turned off for this job.")
    return jn_booking.move(db, job, request.new_date, _person(db, user), request.reason)


class PushRequest(BaseModel):
    job_ids: list[int]


@router.post("/push")
def push_to_jobnimbus(request: PushRequest, db: Session = Depends(get_db),
                      user: ClerkUser = Depends(get_approved_user)):
    from backend.routers.jobs import _person
    from backend.services import jn_booking
    if not can_book(db, user):
        raise HTTPException(status_code=403, detail="Only the office, operations or owners can book jobs in JobNimbus.")
    if jn_booking.mode() == "off":
        raise HTTPException(status_code=409, detail="Sending to JobNimbus is turned off.")
    result = jn_booking.push(db, _person(db, user), job_ids=request.job_ids)
    if result["busy"]:
        raise HTTPException(status_code=409, detail="Someone is already sending jobs to JobNimbus. Try again in a minute.")
    return result
