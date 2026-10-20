"""
Suggested crew notes: what the crew needs to know about the install, added to the work order the crew gets
(its "customer_note" box, where Greg writes "We are NOT replacing gutters", "Contact PM before removing
any decking"...). Nothing reaches the crew until the scheduler approves it on the Weekly Plan, and the whole
feature can be switched off in Settings (crew_notes_enabled).

Two sources:
  1. Gutter scope, read from the work orders (no AI). Crews treat gutters differently when they're being
     replaced, so this line is always suggested for a roof job.
  2. Install instructions an AI finds in the notes, job description and work order notes. Each one must
     quote the note it came from, so the scheduler can check it before approving.
"""
import hashlib
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job
from backend.models.settings import SystemSettings  # noqa: F401  (registers the table)

logger = logging.getLogger("crew_notes")

SETTING_KEY = "crew_notes_enabled"
BUCKETS = ("coming_soon", "to_schedule", "not_built")
MAX_PER_RUN = 40
MAX_AI_LINES = 5
PROMPT_VERSION = 3


def enabled(db: Session) -> bool:
    from backend.models.settings import SystemSettings
    row = db.query(SystemSettings).filter(SystemSettings.key == SETTING_KEY).first()
    return (row.value if row else "true").strip().lower() not in ("false", "off", "0", "no")


def _labor(w: dict) -> list[str]:
    return [(n or "").lower() for n, _ in w.get("labor") or []]


def gutter_line(work_orders: list[dict] | None) -> dict | None:
    """What happens to the gutters, from the work orders. None when there's no roof work order to judge by."""
    wos = work_orders or []
    roof = [w for w in wos if (w.get("trade") or "").lower() in ("roofing", "roof flat", "repairs")]
    if not roof:
        return None
    gutter_items = [n for w in wos if (w.get("trade") or "").lower() == "gutters" for n in _labor(w)]
    roof_items = [n for w in roof for n in _labor(w)]
    if any("gutter install" in n or "downspout" in n for n in gutter_items) or any("remove gutters" in n for n in roof_items):
        text = "Full gutter replacement on this job. The old gutters are coming off."
    elif any("guard" in n for n in gutter_items):
        text = "Gutters are NOT being replaced, only gutter guards added. Protect the gutters."
    else:
        text = "Gutters are NOT being replaced. Protect the gutters."
    if any("detach gutter guards" in n for n in roof_items):
        text += " Detach and reset the gutter guards."
    return {"text": text, "source": "Work orders", "kind": "gutters"}


PROMPT = """You help a roofing company's scheduler write the short notes the {crew} crew reads on its work order.
From the notes below, list ONLY instructions that change how the {crew} crew does THIS install or behaves on site, for example:
- what to protect or be careful with (landscaping, pool, solar panels, skylights, a car that stays in the driveway)
- access: gate code, where to park or put the dumpster, a dog in the yard, a side of the house to avoid
- customer requests for build day (start time, keep a door clear, call before arriving)
- scope details the crew must not miss (which structures, garage included or not, ridge vent, decking to check,
  who to call before removing decking, photos to take)
- product or color, only if a note states it plainly

Leave out: anything about money, insurance, the adjuster, supplements, permits, scheduling, the sales process,
complaints, or the office. Leave out work done by other trades or crews than the {crew} crew; whether the
gutters are being replaced is handled separately.
Leave out anything the crew already sees in the work order's crew notes (given below).
Never guess. Only what a note actually says.

For each item give:
- "text": one short plain sentence for the crew, under 15 words, no symbols or abbreviations they wouldn't use
- "quote": the exact words from the note, copied as written, under 25 words
- "source": where it is, for example "Note by Greg Russell, Oct 19" or "Work order WO-11853"

At most {max_lines} items, most important first. Return ONLY JSON: {{"notes": [...]}}. Empty list if nothing qualifies.

ALREADY ON THE WORK ORDER FOR THE CREW:
{existing}

NOTES:
{notes}"""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def ask_ai(job: Job, existing: str, client=None) -> list[dict] | None:
    if client is None:
        if not settings.ANTHROPIC_API_KEY:
            return None
        client = _client()
    prompt = PROMPT.format(max_lines=MAX_AI_LINES, existing=existing or "(nothing yet)", notes=job.ready_input,
                           crew=crew_word(job))
    try:
        from backend import activity
        with activity.call("claude", "crew notes"):
            response = client.messages.create(
                model=settings.ANTHROPIC_MODEL, max_tokens=700, thinking={"type": "disabled"},
                messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Crew notes failed for job {job.id}: {e}")
        return None
    out = []
    for n in (data.get("notes") or [])[:MAX_AI_LINES] if isinstance(data, dict) else []:
        if isinstance(n, dict) and (n.get("text") or "").strip() and (n.get("quote") or "").strip():
            out.append({"text": n["text"].strip(), "quote": n["quote"].strip(),
                        "source": (n.get("source") or "").strip(), "kind": "notes"})
    return out


# The work order trades whose crew does each primary trade's build
CREW_TRADES = {"roofing": ("roofing", "roof flat", "commercial"), "roofing_repair": ("repairs", "roofing"),
               "siding": ("siding",), "siding_repair": ("repairs", "siding"), "gutters": ("gutters",),
               "windows": ("windows",), "paint": ("exterior painting",), "interior": ("interior",)}


def crew_word(job: Job) -> str:
    return {"roofing_repair": "roofing", "siding_repair": "siding", "paint": "painting"}.get(
        job.primary_trade or "", job.primary_trade or "roofing").upper()


def _main_wo(job: Job) -> dict | None:
    from backend.services.build_days import roofing_work_order
    trades = CREW_TRADES.get(job.primary_trade or "roofing", ("roofing",))
    return (roofing_work_order(job.jn_work_orders) if "roofing" in trades else None) or next(
        (w for w in job.jn_work_orders or [] if (w.get("trade") or "").lower() in trades), None)


def _crew_box(job: Job) -> str:
    """Everything already written for the crew on this trade's work orders."""
    trades = CREW_TRADES.get(job.primary_trade or "roofing", ("roofing",))
    wos = [w for w in job.jn_work_orders or [] if (w.get("customer_note") or "").strip()]
    mine = [w for w in wos if (w.get("trade") or "").lower() in trades]
    # No work order for this trade yet (or it was made as another type): any work order's crew notes count
    return "\n".join(w["customer_note"] for w in (mine or wos))


def input_hash(job: Job) -> str:
    trades = sorted((w.get("trade") or "", tuple(_labor(w))) for w in job.jn_work_orders or [])
    # Bump the version when the rules or prompt change, so every job gets fresh suggestions
    blob = json.dumps([PROMPT_VERSION, job.ready_input or "", _crew_box(job), trades], default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def refresh(job: Job, client=None) -> bool:
    """Rebuild the job's suggestions. False if the AI couldn't run (try again next sync)."""
    lines = []
    existing = _crew_box(job)
    g = gutter_line(job.jn_work_orders)
    # Greg often writes "We are replacing gutters" himself; don't suggest it twice
    if g and (job.primary_trade or "roofing").startswith("roofing") and "gutter" not in existing.lower():
        lines.append(g)
    if (job.ready_input or "").strip():
        found = ask_ai(job, existing, client=client)
        if found is None:
            return False
        lines += found
    # Drop anything the crew already has on the work order, by its wording or by the note it quotes
    have = " ".join(existing.lower().split())
    lines = [ln for ln in lines if " ".join(ln["text"].lower().split()) not in have
             and not (ln.get("quote") and " ".join(ln["quote"].lower().split()) in have)]
    job.crew_note_suggestions = lines
    job.crew_notes_hash = input_hash(job)
    return True


def run(db: Session, client=None, limit: int = MAX_PER_RUN) -> dict:
    """Refresh suggestions for queued jobs whose notes or work orders changed. No-op when switched off."""
    if not enabled(db):
        return {"enabled": False}
    jobs = [j for j in db.query(Job).filter(Job.bucket.in_(BUCKETS)).all()
            if j.jn_work_orders and input_hash(j) != j.crew_notes_hash]
    done = failed = 0
    for job in jobs[:limit]:
        if refresh(job, client=client):
            done += 1
            db.commit()
        else:
            failed += 1
    return {"enabled": True, "refreshed": done, "failed": failed, "waiting": max(0, len(jobs) - limit)}


def approve(db: Session, job: Job, lines: list[str], who: str) -> None:
    clean = []
    for ln in lines:
        t = " ".join((ln or "").split())
        if t and t not in clean:
            clean.append(t)
    job.crew_notes_approved = clean
    job.crew_notes_by = who
    job.crew_notes_at = datetime.utcnow()
    db.commit()


def merged_customer_note(existing: str | None, approved: list[str] | None) -> str | None:
    """The work order's crew notes with the approved lines added (skipping ones already there).
    None when nothing needs adding."""
    existing = (existing or "").rstrip()
    have = " ".join(existing.lower().split())
    add = [ln for ln in approved or [] if " ".join(ln.lower().split()) not in have]
    if not add:
        return None
    return (existing + "\n\n" if existing else "") + "\n".join(add)
