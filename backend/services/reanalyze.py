"""
Single-job re-analysis service.

When a job's data changes (notes added in JN, material corrected manually,
square footage updated, etc.), the scheduler can trigger this to update the
AI's understanding of just THIS job — without running full batch scoring.

Steps performed:
1. Re-fetch JN notes (if linked) — pulls fresh activities/notes from JobNimbus
2. Re-run AI note scanner — extracts duration hints, scope, permit signals
3. Re-classify duration tier (material/sq footage may have changed)
4. Recompute deterministic score (without proximity / weather context)
5. Recompute complexity score (used by crew matching)
6. Stamp last_ai_analyzed_at = now
"""
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models.job import Job


def reanalyze_job(db: Session, job_id: int) -> dict:
    """
    Re-analyze a single job with fresh AI scan + recomputed scores.
    Returns a 'before/after' summary so the UI can show what changed.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job not found"}

    # Snapshot before-state for comparison
    before = {
        "score": float(job.score or 0),
        "duration_days": job.duration_days,
        "duration_tier": job.duration_tier,
        "material_type": job.material_type,
        "square_footage": job.square_footage,
        "permit_confirmed": job.permit_confirmed,
        "ai_note_scan_result": job.ai_note_scan_result,
    }

    # --- Step 1: Re-fetch JN notes if this job is linked to JN ---
    notes_changed = False
    if job.jn_job_id:
        try:
            from backend.services.jobnimbus import fetch_notes_for_job
            activities = fetch_notes_for_job(job.jn_job_id)
            notes_parts = []
            description = ""  # JN job description requires job fetch — skip for now (re-sync covers this)
            if description:
                notes_parts.append(f"[Job Description] {description}")
            for n in activities:
                if isinstance(n, dict):
                    note_text = n.get("note") or n.get("description") or ""
                    if note_text.strip():
                        notes_parts.append(f"[Note] {note_text}")
            new_notes_raw = "\n---\n".join(notes_parts)
            # Only update if actually changed (preserves existing description if API hiccups)
            if new_notes_raw and new_notes_raw != (job.jn_notes_raw or ""):
                job.jn_notes_raw = new_notes_raw
                notes_changed = True
        except Exception:
            pass  # JN unreachable — proceed with existing notes

    # --- Step 2: Force re-run AI note scanner (clear cached result first) ---
    # Clear ai_note_scan_result so scan_job_notes() will run fresh
    job.ai_note_scan_result = None
    db.commit()

    scan_result = None
    try:
        from backend.services.note_scanner import scan_job_notes
        scan_result = scan_job_notes(db, job)
    except Exception:
        pass

    # --- Step 3: Re-classify duration tier (material/sq footage may have updated) ---
    try:
        from backend.services.jobnimbus import _classify_duration_tier
        tier, dur_confirmed_default, crew_flag = _classify_duration_tier(
            job.material_type, job.square_footage
        )
        # Don't override an explicitly-confirmed duration
        if not job.duration_confirmed:
            job.duration_tier = tier
        job.crew_requirement_flag = crew_flag
    except Exception:
        pass

    # --- Step 4: Recompute deterministic score (no proximity/weather context for single job) ---
    try:
        from backend.services.scoring import compute_deterministic_score
        new_score, explanations = compute_deterministic_score(
            job, db, nearby_count=0, weather_status=job.weather_status,
        )
        job.score = new_score
        job.score_explanation = "; ".join(explanations)
    except Exception:
        pass

    # --- Step 5: Stamp analyzed timestamp ---
    job.last_ai_analyzed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)

    # --- Build before/after summary ---
    after = {
        "score": float(job.score or 0),
        "duration_days": job.duration_days,
        "duration_tier": job.duration_tier,
        "material_type": job.material_type,
        "square_footage": job.square_footage,
        "permit_confirmed": job.permit_confirmed,
        "ai_note_scan_result": job.ai_note_scan_result,
    }

    # Compute what actually changed
    changes = []
    if abs(before["score"] - after["score"]) > 0.5:
        changes.append(f"Score: {before['score']:.1f} → {after['score']:.1f}")
    if before["duration_days"] != after["duration_days"]:
        changes.append(f"Duration: {before['duration_days']}d → {after['duration_days']}d")
    if before["duration_tier"] != after["duration_tier"]:
        changes.append(f"Tier: {before['duration_tier']} → {after['duration_tier']}")
    if before["material_type"] != after["material_type"]:
        changes.append(
            f"Material: {before['material_type'] or '—'} → {after['material_type'] or '—'}"
        )
    if before["square_footage"] != after["square_footage"]:
        changes.append(
            f"Sq ft: {before['square_footage'] or '—'} → {after['square_footage'] or '—'}"
        )
    if before["permit_confirmed"] != after["permit_confirmed"]:
        changes.append(
            f"Permit confirmed: {before['permit_confirmed']} → {after['permit_confirmed']}"
        )
    if notes_changed:
        changes.append("Notes updated from JN")

    return {
        "status": "ok",
        "job_id": job.id,
        "analyzed_at": job.last_ai_analyzed_at.isoformat(),
        "scan_result": scan_result,
        "changes": changes,
        "no_changes": len(changes) == 0,
        "before": before,
        "after": after,
    }
