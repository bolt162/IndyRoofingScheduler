"""
AI Note Scanner — uses Claude to extract scheduling-relevant signals from JN notes.
Scans for: duration hints, permit confirmation, material type, square footage,
customer flags, scope details, crew requirements.
Results are cached on the job record (ai_note_scan_result) and re-scanned
when jn_notes_raw changes or when material_type is missing.
"""
import json

import anthropic
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job, JobBucket


# Material aliases for AI-extracted values (same as jobnimbus.py)
_MATERIAL_NORMALIZE = {
    "asphalt": "asphalt", "shingle": "asphalt", "shingles": "asphalt",
    "oc": "asphalt", "owens corning": "asphalt",
    "iko": "asphalt", "gaf": "asphalt",
    "certainteed": "asphalt", "atlas": "asphalt",
    "tamko": "asphalt", "malarkey": "asphalt",
    "polymer modified": "polymer_modified", "modified bitumen": "polymer_modified",
    "tpo": "tpo", "duro-last": "duro_last", "duro last": "duro_last",
    "epdm": "epdm", "coating": "coating",
    "wood shake": "wood_shake", "cedar shake": "wood_shake", "shake": "wood_shake",
    "slate": "slate", "metal": "metal", "standing seam": "metal",
    "siding": "siding",
}


def scan_job_notes(db: Session, job: Job) -> dict | None:
    """Scan a single job's notes with Claude and extract scheduling signals."""
    if not settings.ANTHROPIC_API_KEY:
        return None

    notes_text = job.jn_notes_raw or ""
    description = notes_text.strip()
    if not description:
        return None

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = f"""You are a scheduling assistant for a roofing company. Analyze the following job notes/description and extract any scheduling-relevant signals.

JOB INFO:
- Customer: {job.customer_name}
- Address: {job.address}
- Material Type (from JN): {job.material_type or 'NOT SET — please infer from notes if possible'}
- Square Footage (from JN): {job.square_footage or 'NOT SET — please estimate from notes if possible'}
- Primary Trade: {job.primary_trade or 'unknown'}
- Current Duration Tier: {job.duration_tier or 'unknown'}

JOB NOTES/DESCRIPTION:
{description}

Extract and return a JSON object with these fields:
- "duration_hint": estimated days if mentioned or inferable (integer or null)
- "duration_reason": why you estimated this duration (string or null)
- "permit_signal": true/false/null — any mention of permits being ready or needed
- "material_type_hint": inferred roofing material type if mentioned (one of: "asphalt", "polymer_modified", "tpo", "duro_last", "epdm", "coating", "wood_shake", "slate", "metal", "siding", "other") or null if not determinable. Common brand names: IKO, OC/Owens Corning, GAF, CertainTeed = asphalt shingles.
- "square_footage_hint": estimated square footage if mentioned (number or null). Note: "squares" in roofing = multiply by 100 to get sq ft. E.g. "30 square" = 3000 sq ft.
- "customer_flags": list of strings — any customer concerns (e.g. "called multiple times", "unhappy", "urgent request")
- "scope_details": list of strings — specific scope items found (e.g. "re-deck", "ice and water entire roof", "box vents", "gutters")
- "crew_notes": string or null — any notes about crew requirements (e.g. "needs specialty crew", "steep pitch")
- "multi_day_signal": true/false — does this look like a multi-day job based on scope?
- "priority_signal": "high"/"normal"/"low" — any urgency signals in the notes

Return ONLY valid JSON. No explanation text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Parse JSON, handling markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        # Store result on job
        job.ai_note_scan_result = json.dumps(result)

        # Auto-apply duration hint (spec §4.3: adopt note-derived duration, keep unconfirmed)
        if result.get("duration_hint") and not job.duration_confirmed:
            job.duration_days = result["duration_hint"]
            job.duration_source = f"AI scan: {result.get('duration_reason', 'extracted from notes')}"

        # NOTE: multi_day_signal is kept in ai_note_scan_result for informational
        # display only. We do NOT auto-set is_multi_day — per spec (Section 7.4),
        # multi-day is only set manually via the Scope Change workflow when a crew
        # discovers mid-build that the job needs more time.

        # Auto-apply permit signal
        if result.get("permit_signal") is True and not job.permit_confirmed:
            job.permit_confirmed = True

        # Auto-apply material type hint when JN field is empty
        if result.get("material_type_hint") and not job.material_type:
            hint = result["material_type_hint"].lower().strip()
            # Normalize through alias map
            normalized = _MATERIAL_NORMALIZE.get(hint, hint)
            if normalized in {"asphalt", "polymer_modified", "tpo", "duro_last", "epdm",
                              "coating", "wood_shake", "slate", "metal", "siding", "other"}:
                job.material_type = normalized
                # Re-classify duration tier now that we have material
                from backend.services.jobnimbus import _classify_duration_tier
                tier, dur_confirmed, crew_flag = _classify_duration_tier(
                    job.material_type, job.square_footage
                )
                if not job.duration_confirmed:
                    job.duration_tier = tier
                    job.duration_confirmed = dur_confirmed
                job.crew_requirement_flag = crew_flag

        # Auto-apply square footage hint when JN field is empty
        if result.get("square_footage_hint") and not job.square_footage:
            try:
                sq = float(result["square_footage_hint"])
                if sq > 0:
                    job.square_footage = sq
                    # Re-classify duration tier with new square footage
                    from backend.services.jobnimbus import _classify_duration_tier
                    tier, dur_confirmed, crew_flag = _classify_duration_tier(
                        job.material_type, job.square_footage
                    )
                    if not job.duration_confirmed:
                        job.duration_tier = tier
                        job.duration_confirmed = dur_confirmed
            except (ValueError, TypeError):
                pass

        db.commit()
        return result

    except Exception:
        return None


def scan_all_unscanned_jobs(db: Session) -> dict:
    """
    Scan jobs that have never been scanned (ai_note_scan_result is NULL/empty).
    Jobs that were scanned before are ALWAYS skipped — even if material wasn't extracted.
    This prevents re-scanning the same jobs on every sync and burning API tokens.
    """
    jobs = db.query(Job).filter(
        Job.jn_notes_raw != None,
        Job.jn_notes_raw != "",
        (Job.ai_note_scan_result == None) | (Job.ai_note_scan_result == ""),
    ).all()

    scanned = 0
    failed = 0
    for job in jobs:
        result = scan_job_notes(db, job)
        if result:
            scanned += 1
        else:
            failed += 1

    return {"scanned": scanned, "failed": failed, "total": len(jobs)}
