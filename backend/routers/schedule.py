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
def push_preview(db: Session = Depends(get_db)):
    """Which planned jobs would be sent, and why the others won't. Reads nothing from JobNimbus."""
    from backend.services import jn_booking
    return jn_booking.preview(db)


class PushRequest(BaseModel):
    job_ids: list[int]


@router.post("/push")
def push_to_jobnimbus(request: PushRequest, db: Session = Depends(get_db),
                      user: ClerkUser = Depends(get_approved_user)):
    from backend.routers.jobs import _person
    from backend.services import jn_booking
    if jn_booking.mode() == "off":
        raise HTTPException(status_code=409, detail="Sending to JobNimbus is turned off.")
    result = jn_booking.push(db, _person(db, user), job_ids=request.job_ids)
    if result["busy"]:
        raise HTTPException(status_code=409, detail="Someone is already sending jobs to JobNimbus. Try again in a minute.")
    return result
