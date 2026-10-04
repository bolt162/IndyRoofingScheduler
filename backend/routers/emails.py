"""
Build queue email controls for the office.

Mounted at /api/emails behind the same approved-user check as the rest of the app.
Running a send by hand is admin-only. The public opt-out link lives in main.py.
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.emails import research, runner, team
from backend.emails.config import email_mode, email_mode_raw, smtp_settings, test_recipient
from backend.emails.events import states_for
from backend.models.email import EmailLog, ProductClassification, TeamContact
from backend.models.job import Job
from backend.models.settings import SystemSettings
from backend.services.auth import ClerkUser, get_admin_user, get_approved_user

router = APIRouter()

WEATHER_KEY = "email_weather_slowdown_date"


@router.get("/status")
def status(db: Session = Depends(get_db)):
    team.seed_team(db)
    recent = db.query(EmailLog).order_by(EmailLog.created_at.desc()).limit(50).all()
    weather = db.query(SystemSettings).filter(SystemSettings.key == WEATHER_KEY).first()
    return {
        "mode": email_mode(),
        # What the server actually received, so a mistyped Railway value is easy to spot
        "mode_setting": email_mode_raw(),
        "smtp_ready": bool(smtp_settings()["user"] and smtp_settings()["password"]),
        "test_recipient": test_recipient() or None,
        "weather_slowdown_date": weather.value if weather and weather.value else None,
        "next_thursday": runner.coming_thursday_10am().isoformat(),
        "recent": [{"at": l.created_at.isoformat(), "job_id": l.job_id, "template": l.template,
                    "recipient": l.recipient, "subject": l.subject, "mode": l.mode, "result": l.result,
                    "detail": l.detail} for l in recent],
    }


@router.get("/preview")
def preview(db: Session = Depends(get_db)):
    """What Thursday's send will do. Sends nothing."""
    p = runner.build_preview(db)
    p["text"] = runner.preview_text(p)
    return p


@router.get("/preview/job/{job_id}")
def preview_job_email(job_id: int, db: Session = Depends(get_db)):
    """The actual email a job would get on Thursday, rendered."""
    rc = runner.RunContext(db, runner.coming_thursday_10am())
    for p in runner.plan_weekly(rc):
        if p.job.id == job_id:
            if not p.email:
                return {"template": None, "reason": p.decision.reason}
            return {"template": p.decision.template, "subject": p.email.subject, "html": p.email.html}
    raise HTTPException(404, "Job is not in the build queue")


class WeatherToggle(BaseModel):
    on: bool


@router.post("/weather-slowdown")
def weather_slowdown(body: WeatherToggle, db: Session = Depends(get_db)):
    """Turn the weather slowdown email on for the coming Thursday only (it switches itself off after)."""
    row = db.query(SystemSettings).filter(SystemSettings.key == WEATHER_KEY).first()
    if row is None:
        row = SystemSettings(key=WEATHER_KEY, value="", description="Thursday the weather slowdown email replaces the weekly one")
        db.add(row)
    thursday = runner.coming_thursday_10am()
    row.value = thursday.date().isoformat() if body.on else ""
    db.commit()
    return {"weather_slowdown_date": row.value or None}


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: int, db: Session = Depends(get_db), user: ClerkUser = Depends(get_approved_user)):
    if not db.query(Job).filter(Job.id == job_id).first():
        raise HTTPException(404, "Job not found")
    for st in states_for(db, job_id).values():
        st.suppressed = True
        st.suppressed_reason = f"paused by {user.email or 'office'}"
    db.commit()
    return {"job_id": job_id, "paused": True}


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: int, db: Session = Depends(get_db)):
    for st in states_for(db, job_id).values():
        if (st.suppressed_reason or "") != "unsubscribed":  # a customer opt-out can't be undone here
            st.suppressed = False
            st.suppressed_reason = None
    db.commit()
    return {"job_id": job_id, "paused": False}


# --- Team contacts --------------------------------------------------------

class TeamIn(BaseModel):
    jn_name: str
    display_name: str
    role: str = "rep"
    email: str | None = None
    phone: str | None = None
    is_active: bool = True


def _team_out(r: TeamContact) -> dict:
    return {"id": r.id, "jn_name": r.jn_name, "display_name": r.display_name, "role": r.role,
            "email": r.email, "phone": r.phone, "is_active": r.is_active}


@router.get("/team")
def list_team(db: Session = Depends(get_db)):
    team.seed_team(db)
    return [_team_out(r) for r in db.query(TeamContact).order_by(TeamContact.role, TeamContact.display_name).all()]


@router.post("/team")
def add_team(body: TeamIn, db: Session = Depends(get_db)):
    if body.role not in ("rep", "pm", "ops", "owner"):
        raise HTTPException(400, "role must be rep, pm, ops, or owner")
    row = TeamContact(**body.model_dump())
    row.phone = team.normalize_phone(body.phone) or body.phone
    db.add(row)
    db.commit()
    return _team_out(row)


@router.put("/team/{row_id}")
def update_team(row_id: int, body: TeamIn, db: Session = Depends(get_db)):
    row = db.query(TeamContact).filter(TeamContact.id == row_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    row.phone = team.normalize_phone(body.phone) or body.phone
    db.commit()
    return _team_out(row)


# --- Researched shingle products ------------------------------------------

@router.get("/products")
def list_products(db: Session = Depends(get_db)):
    rows = db.query(ProductClassification).order_by(ProductClassification.created_at.desc()).all()
    return [{"id": r.id, "raw_text": r.raw_text, "display_name": r.display_name, "manufacturer": r.manufacturer,
             "impact_class": r.impact_class, "composition": r.composition, "status": r.status,
             "confidence": r.confidence, "summary": r.summary, "sources": r.sources,
             "reviewed_by": r.reviewed_by} for r in rows]


class ProductReview(BaseModel):
    approve: bool
    impact_class: int | None = None
    composition: str | None = None
    change_class: bool = False


@router.post("/products/{row_id}/review")
def review_product(row_id: int, body: ProductReview, db: Session = Depends(get_db),
                   user: ClerkUser = Depends(get_approved_user)):
    try:
        kwargs = {"impact_class": body.impact_class, "composition": body.composition} if body.change_class else {}
        row = research.review(db, row_id, body.approve, user.email or "office", **kwargs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": row.id, "status": row.status}


# --- Run by hand (admin) ---------------------------------------------------

TASKS = {
    "weekly": runner.run_weekly,
    "welcomes": runner.run_welcomes,
    "reschedules": runner.run_reschedule_checks,
    "scheduled": runner.run_scheduled_emails,
    "long-wait": runner.run_long_wait_alerts,
    "research": runner.run_research,
    "preview": runner.send_preview,
    "samples": runner.send_samples,
}


@router.post("/run/{task}")
def run_task(task: str, db: Session = Depends(get_db), user: ClerkUser = Depends(get_admin_user)):
    if task not in TASKS:
        raise HTTPException(404, f"Unknown task. Choose one of: {', '.join(TASKS)}")
    return {"task": task, "mode": email_mode(), "result": TASKS[task](db)}
