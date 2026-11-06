"""
Emails to ABC Supply (our shingle supplier), from Greg's 2026-11-05 specs. Both go to ABC's two contacts.

  send_postponed()  a build is marked Not Built: tell ABC the delivery is postponed (not for Weather Mid-Build,
                    the material is already on site)
  run_abc_daily()   weekdays about noon: tomorrow's deliveries (Friday: Saturday and Monday)

Where the data lives: JobNimbus material orders are sent straight to ABC. The delivery day is the order's
date_materialorder, the job is in its "related" list, and the ABC order number is the id in supplier.logs once
ABC confirms. Draft orders have none of that and are left out.

Phone numbers for Luke and Greg come from the Team tab (team_contacts), never from code: the repo is shared
with outside developers and Greg's number is for ABC only.
"""
import json
import logging
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.emails.internal import person, team_email
from backend.emails.jn_data import _jn_get
from backend.emails.sender import send
from backend.models.email import EmailLog, TeamContact
from backend.models.job import Job

logger = logging.getLogger("emails.abc")
TZ = ZoneInfo("America/Indiana/Indianapolis")
DAILY = "abc_daily"
POSTPONED = "abc_postponed"
NO_POSTPONE_REASON = "Weather Mid-Build"   # material is already on site
NOT_SENT_STATUSES = ("draft", "cancelled", "canceled")
DELIVERED_STATUSES = ("fulfilled", "delivered", "invoiced")
# Labor orders (JobNimbus work orders) whose build uses ABC material. Gutters never email ABC.
ABC_TRADES = ("roofing", "siding")
# Buckets where a booked labor order is a real build (scheduled roofs, follow-up siding)
BUILD_BUCKETS = ("scheduled", "other_trades")
# Where bucket says the build is not booked, so ABC was already told (or will be) it moved
OFF_THE_LIST_BUCKETS = ("to_schedule", "not_built")


def recipients() -> list[str]:
    raw = os.getenv("ABC_EMAIL_TO") or "donald.charles@abcsupply.com,michael.garner@abcsupply.com"
    return [a.strip() for a in raw.split(",") if a.strip()]


# --- Days -----------------------------------------------------------------------------------------------

def delivery_days(today: date) -> list[date]:
    """The days the reminder covers. Mon-Thu: tomorrow. Friday: Saturday and Monday. Nothing on a weekend.
    Holidays don't matter (Aaron, 2026-11-05): what goes out depends only on the jobs scheduled."""
    if today.weekday() >= 5:
        return []
    if today.weekday() == 4:
        return [today + timedelta(days=1), today + timedelta(days=3)]
    return [today + timedelta(days=1)]


def _day(d: date) -> str:
    return f"{d:%A}, {d:%b} {d.day}"


# --- JobNimbus ------------------------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"[‪-‮⁦-⁩]", "", text or "").strip()


def parse_order(o: dict) -> dict | None:
    """One ABC material order -> what the emails show, or None for a draft / non-ABC order."""
    sup = o.get("supplier") or {}
    if (sup.get("type") or "") != "ABC Supply" or (o.get("status_name") or "").lower() in NOT_SENT_STATUSES:
        return None
    job = next((r for r in o.get("related") or [] if r.get("type") == "job"), {})
    number = job.get("number") or ""
    customer = _clean(job.get("name") or "")
    customer = re.sub(r"\s+-\s+J-\d+.*$", "", customer)   # "David Boyd - J-25770 (1)" -> "David Boyd"
    # The ABC order number is the "orderReceived" log id (C12-...; it is the Reference on ABC's invoice). A later
    # "fulfilled" log holds the invoice number, which is not the order number.
    ids = [str(x["id"]) for x in sup.get("logs") or [] if x.get("id") and x.get("msg") in (None, "orderReceived")]
    a = o.get("address") or {}
    ts = o.get("date_materialorder") or 0
    return {"jn_job_id": job.get("id"), "job_number": number, "customer": customer,
            "open": (o.get("status_name") or "").lower() not in DELIVERED_STATUSES,
            "address": ", ".join(p for p in (a.get("address_line1"), a.get("city")) if p),
            "abc_order": ids[-1] if ids else "", "day": datetime.fromtimestamp(ts, TZ).date() if ts else None}


def _orders(filter_: dict) -> list[dict]:
    data = _jn_get("v2/materialorders", params={"filter": json.dumps(filter_), "size": 500})
    return [p for p in (parse_order(o) for o in (data.get("results") or [])) if p]


def fetch_deliveries(days: list[date]) -> list[dict]:
    start = int(datetime.combine(min(days), time.min, TZ).timestamp())
    end = int(datetime.combine(max(days) + timedelta(days=1), time.min, TZ).timestamp())
    rng = {"must": [{"range": {"date_materialorder": {"gte": start, "lt": end}}}]}
    return [p for p in _orders(rng) if p["day"] in days]


def fetch_job_orders(jn_job_id: str) -> list[dict]:
    """Every sent ABC order on the job, newest first."""
    return _orders({"must": [{"term": {"related.id": jn_job_id}}]})


def fetch_job_order(jn_job_id: str) -> dict | None:
    """The newest confirmed ABC order on the job that ABC hasn't delivered yet (else the newest confirmed one)."""
    orders = [o for o in fetch_job_orders(jn_job_id) if o["abc_order"]]
    return next((o for o in orders if o["open"]), orders[0] if orders else None)


def labor_day(job: Job) -> date | None:
    """The day the job's roofing or siding labor order is booked (Pending Start), or None. When Greg moves a
    build, this date moves; the material order's date can't (JobNimbus locks it once ABC has it)."""
    days = [w.get("start") for w in job.jn_work_orders or []
            if (w.get("trade") or "").strip().lower() in ABC_TRADES
            and (w.get("status") or "").strip().lower() == "pending start" and w.get("start")]
    return date.fromisoformat(min(days)) if days else None


def deliveries(db: Session, days: list[date], by_date: list[dict], job_orders) -> list[dict]:
    """What ABC should bring on `days` (Aaron, 2026-11-06):
      1. every build booked on those days (its roofing or siding labor order), with its open ABC order; a build
         moved from another day says so, because its material order still shows the old day
      2. every ABC order dated those days, unless its build is now booked for another day or is back in the queue
    A booked build with no ABC order is left out (it may use another supplier) and noted in the Activity Log."""
    jobs = {j.jn_job_id: j for j in db.query(Job).filter(Job.jn_job_id.isnot(None)).all()}
    out, seen = [], set()
    for j in jobs.values():
        day = labor_day(j)
        if day not in days or j.bucket not in BUILD_BUCKETS:
            continue
        orders = [o for o in job_orders(j.jn_job_id) if o["abc_order"] and o["open"]]
        order = next((o for o in orders if o["day"] == day), orders[0] if orders else None)
        if not order:
            _log(db, DAILY, "", "skipped", f"{j.customer_name}: booked for {_day(day)} but no open ABC order", j.id)
            continue
        moved = order["day"] and order["day"] != day
        out.append({**order, "day": day, "moved_from": order["day"] if moved else None})
        seen.add(j.jn_job_id)
    for o in by_date:
        j = jobs.get(o["jn_job_id"])
        if o["jn_job_id"] in seen or (j and (j.bucket in OFF_THE_LIST_BUCKETS or labor_day(j) not in (None, o["day"]))):
            continue
        out.append({**o, "moved_from": None})
        seen.add(o["jn_job_id"])
    return sorted(out, key=lambda d: (d["day"], d["job_number"]))


# --- Contacts and sending -------------------------------------------------------------------------------

def _contact(db: Session, role: str) -> TeamContact | None:
    return db.query(TeamContact).filter(TeamContact.is_active.is_(True), TeamContact.role == role).first()


def _log(db: Session, template: str, mode: str, result: str, detail: str, job_id: int | None = None,
         at: datetime | None = None) -> None:
    from backend import activity
    activity.write("email", "smtp", f"{template}: {detail}"[:160], status={"failed": "error"}.get(result, "skipped"),
                   job_id=job_id, detail=detail)
    if result == "failed":  # a sent email is logged by send(); a failure here counts as today's one try
        db.add(EmailLog(job_id=job_id, template=template, recipient="", subject=None, mode=mode, result=result, detail=detail,
                          created_at=at or datetime.utcnow()))
        db.commit()


def _sent_today(db: Session, mode: str, today: date) -> bool:
    start = datetime.combine(today, time.min, TZ).astimezone(timezone.utc).replace(tzinfo=None)
    return db.query(EmailLog).filter(EmailLog.template == DAILY, EmailLog.mode == mode, EmailLog.created_at >= start,
                                     EmailLog.result.in_(("sent", "failed"))).first() is not None


def _contacts_block(db: Session) -> str | None:
    luke, greg = _contact(db, "pm"), _contact(db, "ops")
    if not (luke and luke.phone and greg and greg.phone):
        return None
    from backend.emails.internal import format_phone
    return (f"- {luke.display_name}, Lead PM: {format_phone(luke.phone)}\n"
            f"- {greg.display_name}: {format_phone(greg.phone)}")


def run_abc_daily(db: Session, now: datetime | None = None, mode: str | None = None, fetch=None,
                  fetch_job=None) -> dict:
    from backend.emails.config import email_mode
    mode = mode or email_mode()
    now = now or datetime.utcnow()
    today = now.replace(tzinfo=timezone.utc).astimezone(TZ).date()
    days = delivery_days(today)
    if not days:
        _log(db, DAILY, mode, "skipped", f"{today:%A} is a weekend")
        return {"sent": False, "why": "weekend"}
    if _sent_today(db, mode, today):
        return {"sent": False, "why": "already sent today"}
    contacts = _contacts_block(db)
    if not contacts:
        _log(db, DAILY, mode, "failed", "Luke's or Greg's phone number is missing on the Team tab", at=now)
        return {"sent": False, "why": "missing phone"}
    try:
        found = deliveries(db, days, (fetch or fetch_deliveries)(days), fetch_job or fetch_job_orders)
    except Exception as e:  # noqa: BLE001
        _log(db, DAILY, mode, "failed", f"JobNimbus didn't answer ({type(e).__name__}); no reminder sent", at=now)
        _tell_ops(db, mode, "JobNimbus didn't answer, so the ABC delivery reminder did not go out today.")
        return {"sent": False, "why": "jobnimbus"}
    when = " and ".join(_day(d) for d in days)
    if not found:  # no deliveries, no email (Aaron, 2026-11-05)
        _log(db, DAILY, mode, "skipped", f"no deliveries for {when}")
        return {"sent": False, "why": "no deliveries"}
    lead = f"This is a heads-up on the material deliveries we have scheduled for {when}."
    multi = len(days) > 1
    notes = any(d["moved_from"] for d in found)
    cols = (["Day"] if multi else []) + ["Job #", "ABC order #", "Customer", "Address"] + (["Note"] if notes else [])
    rows = [([_day(d["day"])] if multi else []) + [d["job_number"], d["abc_order"] or "Pending", person(d["customer"]),
                                                   d["address"]]
            + ([f"Rescheduled from {_day(d['moved_from'])}" if d["moved_from"] else ""] if notes else []) for d in found]
    items = (cols, rows)
    email = team_email(DAILY, f"Material deliveries for {when}", lead, "**Contacts**",
                       [], extra=[contacts, "This is a reminder of upcoming deliveries. Changes may still come from our PM or a "
                                  "separate postponement notice. Questions? Contact Luke or Greg above."], items=items)
    ok = send(db, None, email, recipients(), customer_name="ABC Supply", mode=mode)
    return {"sent": ok, "deliveries": len(found)}


def _tell_ops(db: Session, mode: str, message: str) -> None:
    from backend.emails.runner import _ops_and_pms
    to = _ops_and_pms(db)
    if to:
        send(db, None, team_email("internal", "The ABC delivery reminder did not go out", message,
                                  "Send ABC today's deliveries yourself.", []), to, mode=mode)


def send_postponed(db: Session, job: Job, reason: str, mode: str | None = None, fetch=None, trade: str | None = None) -> dict:
    """Not Built: tell ABC the delivery is postponed. Never raises into the Not Built save (the caller wraps it)."""
    from backend.emails.config import email_mode
    mode = mode or email_mode()
    if (trade or job.primary_trade or "").lower() == "gutters":  # gutters never email ABC; siding does, if an order is on file
        _log(db, POSTPONED, mode, "skipped", f"{job.customer_name}: gutters don't use ABC material", job.id)
        return {"sent": False, "why": "gutters"}
    if reason == NO_POSTPONE_REASON:
        _log(db, POSTPONED, mode, "skipped", f"{job.customer_name}: {reason}, material already on site", job.id)
        return {"sent": False, "why": "mid-build"}
    try:
        order = (fetch or fetch_job_order)(job.jn_job_id) if job.jn_job_id else None
    except Exception as e:  # noqa: BLE001
        _log(db, POSTPONED, mode, "failed", f"{job.customer_name}: JobNimbus didn't answer ({type(e).__name__})", job.id)
        return {"sent": False, "why": "jobnimbus"}
    if not order:
        _log(db, POSTPONED, mode, "skipped", f"{job.customer_name}: no confirmed ABC order on the job", job.id)
        return {"sent": False, "why": "no order"}
    email = team_email(POSTPONED, f"Delivery postponed: {person(job.customer_name)}, {order['job_number']}",
                       "The material delivery for this job has been postponed. We'll send a new delivery date as soon "
                       "as we have one.", "", [("Customer", person(job.customer_name)), ("Address", order["address"]),
                                                ("Job #", order["job_number"]), ("ABC order #", order["abc_order"])])
    return {"sent": send(db, job.id, email, recipients(), customer_name="ABC Supply", mode=mode)}
