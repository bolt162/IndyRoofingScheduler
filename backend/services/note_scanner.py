"""
AI Note Scanner — uses Claude to extract scheduling-relevant signals from JN notes.
Scans for: duration hints, permit confirmation, customer flags, scope details.
Results are cached on the job record (ai_note_scan_result) and only re-scanned
when jn_notes_raw changes.
"""
import json

import anthropic
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job, JobBucket


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
- Material Type: {job.material_type or 'unknown'}
- Square Footage: {job.square_footage or 'unknown'}
- Current Duration Tier: {job.duration_tier or 'unknown'}

JOB NOTES/DESCRIPTION:
{description}

Extract and return a JSON object with these fields:
- "duration_hint": estimated days if mentioned (integer or null)
- "duration_reason": why you estimated this duration (string or null)
- "permit_signal": true/false/null — any mention of permits being ready or needed
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

        # Auto-apply signals to job fields
        if result.get("duration_hint") and not job.duration_confirmed:
            job.duration_days = result["duration_hint"]
            job.duration_source = f"AI scan: {result.get('duration_reason', 'extracted from notes')}"

        if result.get("multi_day_signal") and not job.is_multi_day:
            job.is_multi_day = True

        if result.get("permit_signal") is True and not job.permit_confirmed:
            job.permit_confirmed = True

        db.commit()
        return result

    except Exception:
        return None


def scan_all_unscanned_jobs(db: Session) -> dict:
    """Scan all jobs that haven't been scanned yet or have notes but no scan result."""
    jobs = db.query(Job).filter(
        Job.jn_notes_raw != None,
        Job.jn_notes_raw != "",
        Job.ai_note_scan_result == None,
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
