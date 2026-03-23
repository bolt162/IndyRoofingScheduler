from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db
from backend.models.settings import SystemSettings
from backend.models.pm import PM, Crew

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


@router.post("/crews")
def add_crew(name: str, specialties: list[str] | None = None, db: Session = Depends(get_db)):
    crew = Crew(name=name, specialties=specialties or [])
    db.add(crew)
    db.commit()
    db.refresh(crew)
    return crew
