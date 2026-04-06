from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db, engine, Base
from backend.models.settings import SystemSettings, DEFAULT_SETTINGS
from backend.models.pm import PM, Crew
from backend.models.job import Job
from backend.models.schedule import SchedulePlan
from backend.models.note_log import NoteLog

router = APIRouter()


class SettingUpdate(BaseModel):
    value: str


@router.get("/")
def get_all_settings(db: Session = Depends(get_db)):
    settings = db.query(SystemSettings).all()
    return {s.key: {"value": s.value, "description": s.description} for s in settings}


@router.put("/{key}")
def update_setting(key: str, update: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    if not setting:
        return {"error": f"Setting '{key}' not found"}
    setting.value = update.value
    db.commit()
    return {"key": key, "value": update.value}


# PM management
@router.get("/pms")
def list_pms(db: Session = Depends(get_db)):
    return db.query(PM).all()


@router.post("/pms")
def add_pm(name: str, baseline: int = 3, max_cap: int = 5, db: Session = Depends(get_db)):
    pm = PM(name=name, baseline_capacity=baseline, max_capacity=max_cap)
    db.add(pm)
    db.commit()
    db.refresh(pm)
    return pm


# Crew management
@router.get("/crews")
def list_crews(db: Session = Depends(get_db)):
    return db.query(Crew).all()


class CrewCreate(BaseModel):
    name: str
    specialties: list[str] = []


@router.post("/crews")
def add_crew(data: CrewCreate, db: Session = Depends(get_db)):
    crew = Crew(name=data.name, specialties=data.specialties or [])
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return crew


class CrewUpdate(BaseModel):
    name: str | None = None
    specialties: list[str] | None = None
    is_active: bool | None = None


@router.patch("/crews/{crew_id}")
def update_crew(crew_id: int, update: CrewUpdate, db: Session = Depends(get_db)):
    crew = db.query(Crew).filter(Crew.id == crew_id).first()
    if not crew:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Crew not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(crew, field, value)
    db.commit()
    db.refresh(crew)
    return crew


@router.delete("/crews/{crew_id}")
def delete_crew(crew_id: int, db: Session = Depends(get_db)):
    crew = db.query(Crew).filter(Crew.id == crew_id).first()
    if not crew:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Crew not found")
    db.delete(crew)
    db.commit()
    return {"status": "ok", "deleted": crew_id}


@router.post("/reset-db")
def reset_database(db: Session = Depends(get_db)):
    """Reset the entire database — drops all jobs, PMs, crews, notes, plans, and re-seeds settings."""
    # Delete all data in order (foreign key safe)
    db.query(NoteLog).delete()
    db.query(SchedulePlan).delete()
    db.query(Job).delete()
    db.query(Crew).delete()
    db.query(PM).delete()
    db.query(SystemSettings).delete()
    db.commit()

    # Re-seed default settings
    for key, info in DEFAULT_SETTINGS.items():
        db.add(SystemSettings(key=key, value=info["value"], description=info["description"]))
    db.commit()

    return {"status": "ok", "message": "Database reset. All jobs, PMs, crews, notes, and plans cleared. Settings re-seeded."}
