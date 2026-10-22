from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from typing import Literal

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


# --- Suggest builds: pencil in the rest of a week; nothing is saved as a plan until it's kept ---

class SuggestRequest(BaseModel):
    week_start: date
    pm_ids: list[int] | None = None
    kind: Literal["roofs", "gutters", "siding"] = "roofs"


class SuggestionsRequest(BaseModel):
    job_ids: list[int] | None = None
    week_start: date | None = None


@router.post("/suggest")
def suggest_builds(request: SuggestRequest, db: Session = Depends(get_db),
                   user: ClerkUser = Depends(get_approved_user)):
    from backend.services import suggest
    return suggest.suggest_week(db, request.week_start, pm_ids=request.pm_ids, kind=request.kind)


@router.post("/suggestions/keep")
def keep_suggestions(request: SuggestionsRequest, db: Session = Depends(get_db),
                     user: ClerkUser = Depends(get_approved_user)):
    from backend.models.job import Job
    from backend.routers.jobs import _person
    from backend.services import suggest
    ids = request.job_ids
    if ids is None and request.week_start:
        monday = request.week_start - timedelta(days=request.week_start.weekday())
        ids = [j.id for j in db.query(Job).filter(Job.suggested_date >= monday,
                                                  Job.suggested_date < monday + timedelta(days=7)).all()]
    return {"kept": suggest.keep(db, ids or [], _person(db, user))}


@router.post("/suggestions/clear")
def clear_suggestions(request: SuggestionsRequest, db: Session = Depends(get_db),
                      user: ClerkUser = Depends(get_approved_user)):
    from backend.services import suggest
    if request.job_ids is None and request.week_start is None:
        raise HTTPException(status_code=400, detail="Say which jobs or which week.")
    return {"cleared": suggest.clear(db, week_start=request.week_start, job_ids=request.job_ids)}
