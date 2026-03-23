from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.schedule import SchedulePlan

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
