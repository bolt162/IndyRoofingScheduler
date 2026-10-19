"""
What JobNimbus has on the calendar, read during every sync (READ-ONLY).

How Greg books a build in JobNimbus (checked on J-26819 and J-26845, 2026-10-19): on the trade's
work order he enters the start date, adds the crew and Luke Mroz as subcontractors, sends it to the
crew, then moves the work order to Pending Start and the job to Pending Start Date. So the work
orders in Pending Start are the real calendar; the job's own start date is the fallback.

Also builds the text the ready check reads: dated notes plus each work order's notes.
"""
import hashlib
import html
import re
from datetime import date, datetime

PENDING_START = "pending start"
# Our own people show up as subcontractors on work orders ("Luke Mroz - Indy Roof and Restoration")
OUR_COMPANY = "indy roof"

# Activities people write that can hold a reason not to build yet. Supplements are the
# Estimating Dept's updates ("adjuster confirmed this is under review").
READY_ACTIVITY_TYPES = {"note", "phone call", "comment", "comment (migrated)", "supplements"}
# Notes the system writes itself, including the ready check's own answers
READY_SKIP_PREFIXES = ("[SCHEDULER SYSTEM", "[BUILD QUEUE EMAIL", "SCHEDULING CHECK:")
MAX_READY_CHARS = 14000


def _date(ts) -> date | None:
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts).date()
    return None


def _plain(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", text or "", flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()).strip()


def split_subs(subs: list[dict] | None) -> tuple[list[str], str | None]:
    """(crew names, our PM's name) from a work order's or job's subcontractors."""
    crews, pm = [], None
    for s in subs or []:
        name = (s.get("name") or "").strip() if isinstance(s, dict) else ""
        if not name:
            continue
        if OUR_COMPANY in name.lower():
            pm = pm or name.split(" - ")[0].strip()
        elif name not in crews:
            crews.append(name)
    return crews, pm


def summarize_work_orders(wos: list[dict]) -> list[dict]:
    out = []
    for w in wos or []:
        if not isinstance(w, dict) or w.get("is_active") is False or w.get("is_archived"):
            continue
        crews, pm = split_subs(w.get("subcontractors"))
        start = _date(w.get("date_start"))
        out.append({
            "number": w.get("number") or "",
            "trade": w.get("record_type_name") or "",
            "status": w.get("status_name") or "",
            "start": start.isoformat() if start else None,
            "crews": crews,
            "pm": pm,
            "internal_note": _plain(w.get("internal_note") or ""),
            "customer_note": _plain(w.get("customer_note") or ""),
        })
    out.sort(key=lambda w: w["number"])
    return out


def calendar_from(jn_job: dict, work_orders: list[dict]) -> tuple[date | None, list[str], str | None]:
    """(start date, crews, PM) JobNimbus has for the job's next build."""
    pending = [w for w in work_orders if w["status"].strip().lower() == PENDING_START and w["start"]]
    if pending:
        first = min(pending, key=lambda w: w["start"])
        return date.fromisoformat(first["start"]), first["crews"], first["pm"]
    crews, pm = split_subs(jn_job.get("subcontractors"))
    return _date(jn_job.get("date_start")), crews, pm


def build_ready_input(description: str, activities: list[dict], work_orders: list[dict]) -> str:
    """Everything a person wrote that could hold the build: work order notes, then dated notes, newest first."""
    parts = []
    if (description or "").strip():
        parts.append(f"[Job description] {_plain(description)}")
    for w in work_orders:
        bits = [f"{label}: {w[key]}" for key, label in (("internal_note", "internal note"),
                                                        ("customer_note", "special instructions")) if w[key]]
        if bits:
            parts.append(f"[Work order {w['number']}, {w['trade'] or 'trade not set'}, status {w['status'] or 'none'}] "
                         + "; ".join(bits))
    total = sum(len(p) for p in parts)
    notes = [a for a in activities or [] if isinstance(a, dict)
             and (a.get("record_type_name") or "").strip().lower() in READY_ACTIVITY_TYPES]
    notes.sort(key=lambda a: a.get("date_created") or 0, reverse=True)
    for a in notes:
        text = _plain(a.get("note") or "")
        if not text or text.upper().startswith(READY_SKIP_PREFIXES):
            continue
        when = _date(a.get("date_created"))
        who = a.get("created_by_name") or "someone"
        line = f"[{when:%b %-d, %Y} {who}, {a.get('record_type_name')}] {text}" if when else f"[{who}] {text}"
        if total + len(line) > MAX_READY_CHARS:
            break
        parts.append(line)
        total += len(line)
    return "\n---\n".join(parts)


def input_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()
