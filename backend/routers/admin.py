"""
Owner/admin-only endpoints. Mounted at /api/admin with get_owner_or_admin on every route.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.activity import ActivityLog
from backend.database import get_db

router = APIRouter()


@router.get("/activity")
def activity_log(
    db: Session = Depends(get_db),
    kind: str | None = None,
    source: str | None = None,
    status: str | None = None,
    q: str | None = Query(None, description="Text search in action, detail, and who"),
    before_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Newest first. Page backwards with before_id = the last row's id."""
    query = db.query(ActivityLog)
    if kind:
        query = query.filter(ActivityLog.kind == kind)
    if source:
        query = query.filter(ActivityLog.source == source)
    if status:
        query = query.filter(ActivityLog.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(ActivityLog.action.ilike(like), ActivityLog.detail.ilike(like),
                                 ActivityLog.actor.ilike(like)))
    if before_id:
        query = query.filter(ActivityLog.id < before_id)
    rows = query.order_by(ActivityLog.id.desc()).limit(limit).all()
    return {
        "rows": [{"id": r.id, "at": r.at.isoformat(), "kind": r.kind, "source": r.source, "action": r.action,
                  "status": r.status, "actor": r.actor, "job_id": r.job_id, "duration_ms": r.duration_ms,
                  "detail": r.detail} for r in rows],
        "more": len(rows) == limit,
        "server_time": datetime.utcnow().isoformat(),
    }
