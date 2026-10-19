"""
Ready check: before a job is scheduled, AI reads its notes for anything that would stop the build
(colors not picked, waiting on an estimate or approval, customer asked us to wait...).

Aaron, 2026-10-19: flag it up front on the job, let Nikka, Ross or Greg answer "OK, it's fine"
(a note is just missing) or "Keep on hold", and push the rest through.

Statuses (Job.ready_status):
  clear    nothing in the notes holds it up
  flagged  something might; waiting for someone to answer
  ok       someone said it's fine (stays OK until the notes raise something new)
  hold     someone said wait; clears itself when a later note fixes it
The check reruns only when the job's notes change (Job.ready_input_hash).
"""
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job
from backend.services.schedule_sync import input_hash

logger = logging.getLogger("ready_check")

# Jobs worth checking: coming up, waiting to be scheduled, or sent back to the queue
READY_BUCKETS = ("coming_soon", "to_schedule", "not_built")
OPEN_STATUSES = ("flagged", "hold")
MAX_PER_RUN = 60  # first run backfills in a few syncs instead of one long one

PROMPT = """You check a roofing and restoration job's notes before the office schedules the build.
List anything the notes say is still missing or pending that would STOP the crew from doing the work if we booked it now.

Counts as a blocker:
- Product, color or style not picked or not confirmed (shingle, siding, gutter, trim)
- A color field on a work order left blank (for example "Wilco Color Selection:" with nothing after it)
- Waiting on an estimate, change order or approval the work depends on
- Insurance approval still needed before work can start
- Permit or HOA approval not in yet
- Deposit, financing or payment that must come before starting, not received yet
- Customer asked us to wait, hold off or not schedule yet
- Materials not available yet, or a special order not in
- Scope still undecided (for example, waiting to hear if they add gutters)
- A question to the rep or customer that has to be answered before building

Not a blocker:
- Anything a newer note already settled. Notes are newest first, so a newer note can settle an older one.
- Insurance supplements for more money that don't stop the work, unless a note says to wait for them
- Weather, routine updates, payment reminders after the build, punch list items
- Guesses. Only flag what the notes actually say.

For each blocker give:
- "issue": a short plain sentence for the office, under 12 words, naming the trade if it's not the roof (for example "Gutter color not picked yet")
- "quote": the exact words from the note that show it, copied as written, under 25 words
- "source": where it is, for example "Note by Greg Russell, Oct 19" or "Work order WO-11854"

Return ONLY JSON: {{"blockers": [...]}}. Use an empty list when nothing holds the job up.

JOB: {customer} ({trade}), JobNimbus status {status}

NOTES:
{notes}"""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def ask_ai(job: Job, client=None) -> list[dict] | None:
    """The blockers the AI finds in the job's notes, or None if the check couldn't run."""
    if client is None:
        if not settings.ANTHROPIC_API_KEY:
            return None
        client = _client()
    prompt = PROMPT.format(customer=job.customer_name, trade=job.primary_trade or "trade not set",
                           status=job.jn_status or "unknown", notes=job.ready_input)
    try:
        from backend import activity
        with activity.call("claude", "ready check"):
            response = client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=800,
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": prompt}],
            )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Ready check failed for job {job.id}: {e}")
        return None
    blockers = []
    for b in (data.get("blockers") or []) if isinstance(data, dict) else []:
        if isinstance(b, dict) and (b.get("issue") or "").strip():
            blockers.append({"issue": b["issue"].strip(), "quote": (b.get("quote") or "").strip(),
                             "source": (b.get("source") or "").strip()})
    return blockers


def _keys(flags: list[dict] | None) -> set[str]:
    return {" ".join((f.get("quote") or f.get("issue") or "").lower().split()) for f in flags or []}


def apply_result(job: Job, blockers: list[dict], now: datetime | None = None) -> None:
    """Set the job's ready status from a fresh check, keeping the office's answer when it still applies."""
    job.ready_flags = blockers
    job.ready_checked_at = now or datetime.utcnow()
    job.ready_input_hash = input_hash(job.ready_input or "")
    if not blockers:
        job.ready_status = "clear"
    elif job.ready_status == "ok" and _keys(blockers) <= set(job.ready_ok_quotes or []):
        pass  # same things someone already said were fine
    elif job.ready_status == "hold":
        pass  # still waiting; stays on hold until the notes settle it or someone says OK
    else:
        job.ready_status = "flagged"


def needs_check(job: Job) -> bool:
    return (job.bucket in READY_BUCKETS and job.ready_input is not None
            and input_hash(job.ready_input) != job.ready_input_hash)


def run_ready_checks(db: Session, client=None, limit: int = MAX_PER_RUN) -> dict:
    """Check every job whose notes changed since its last check. Cheap no-op when none did."""
    jobs = [j for j in db.query(Job).filter(Job.bucket.in_(READY_BUCKETS), Job.ready_input.isnot(None)).all()
            if needs_check(j)]
    checked = failed = 0
    for job in jobs[:limit]:
        if not (job.ready_input or "").strip():
            apply_result(job, [])
            checked += 1
            continue
        blockers = ask_ai(job, client=client)
        if blockers is None:
            failed += 1
            continue
        apply_result(job, blockers)
        checked += 1
        db.commit()
    db.commit()
    return {"checked": checked, "failed": failed, "waiting": max(0, len(jobs) - limit)}


def _issues(flags: list[dict] | None) -> str:
    items = [f["issue"].rstrip(".") for f in flags or [] if f.get("issue")]
    if not items:
        return "something in the notes"
    return items[0] if len(items) == 1 else "; ".join(items)


def decision_note(decision: str, flags: list[dict] | None, who: str, note: str | None) -> str:
    """The note left in JobNimbus. Starts with "Scheduling check:" so the checks skip their own notes."""
    extra = f" Their note: {note.strip()}" if (note or "").strip() else ""
    if decision == "ok":
        return (f"Scheduling check: OK to schedule. The notes looked like this might hold the job up: "
                f"{_issues(flags)}. {who} checked and said it can be scheduled.{extra}")
    return f"Scheduling check: on hold, don't schedule yet. Waiting on: {_issues(flags)}. Set by {who}.{extra}"


def record_decision(db: Session, job: Job, decision: str, who: str, note: str | None = None,
                    push=None) -> dict:
    """Save the office's answer and leave a note on the job in JobNimbus."""
    if decision not in ("ok", "hold"):
        raise ValueError("decision must be ok or hold")
    job.ready_status = decision
    job.ready_ok_quotes = sorted(_keys(job.ready_flags)) if decision == "ok" else []
    job.ready_decision_by = who
    job.ready_decision_at = datetime.utcnow()
    job.ready_decision_note = (note or "").strip() or None
    db.commit()
    text = decision_note(decision, job.ready_flags, who, note)
    pushed = False
    if job.jn_job_id:
        if push is None:
            from backend.services.jobnimbus import push_note_to_jn as push
        try:
            push(job.jn_job_id, text)
            pushed = True
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ready decision note to JobNimbus failed for job {job.id}: {e}")
    return {"status": job.ready_status, "note": text, "pushed_to_jn": pushed}


def open_items(db: Session) -> list[Job]:
    """Jobs waiting for an answer or on hold, oldest check first."""
    jobs = db.query(Job).filter(Job.bucket.in_(READY_BUCKETS), Job.ready_status.in_(OPEN_STATUSES)).all()
    return sorted(jobs, key=lambda j: (j.ready_status != "flagged", j.ready_checked_at or datetime.min))
