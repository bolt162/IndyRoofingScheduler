from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db

router = APIRouter()


@router.post("/run")
def run_scoring(
    pm_ids: list[int] | None = None,
    target_date: str | None = None,
    db: Session = Depends(get_db),
):
    from backend.services.scoring import run_scoring_engine
    result = run_scoring_engine(db, pm_ids=pm_ids, target_date=target_date)
    return result


@router.post("/scan-notes")
def scan_notes(db: Session = Depends(get_db)):
    """Scan all unscanned job notes with AI to extract scheduling signals."""
    from backend.services.note_scanner import scan_all_unscanned_jobs
    return scan_all_unscanned_jobs(db)
