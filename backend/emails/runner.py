"""
The email engine: decides who gets what, sends it, and records it.

Entry points (called by the timers in main.py, the dry-run command, and the API):
  run_weekly()            Thursday 10:00   weekly update for every queued customer
  run_welcomes()          daily            Welcome for jobs that just entered the queue
  run_reschedule_checks() daily 17:00      same-day reschedule emails + PM/rep alert
  run_scheduled_emails()  every 30 min     fun "you're on the calendar" email
  run_long_wait_alerts()  daily            Greg + rep at 10 weeks, then every 2 weeks
  run_research()          daily            research unknown shingle products
  build_preview()         Wednesday        what Thursday will send (nothing is sent)

Safety:
  EMAIL_MODE=off   nothing sends and no progress is recorded
  EMAIL_MODE=test  every email goes to EMAIL_TEST_RECIPIENT; progress is kept in the
                   "test" state rows, so it never counts as a customer send
  EMAIL_MODE=live  real recipients; every customer email is copied to a JobNimbus note
"""
import logging
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.emails import compose as K
from backend.emails import copy as C
from backend.emails import markup, research, selector as S, team
from backend.emails.compose import ComposedEmail, EmailContext, compose
from backend.emails.config import email_mode, office_alert_recipient
from backend.emails.events import DONE_BUCKETS, states_for
from backend.emails.jn_data import JobDetails, fetch_job_details, jn_schedule_email_sent
from backend.emails.sender import send
from backend.models.email import EmailLog, EmailState, JobEvent, TeamContact
from backend.models.job import Job

logger = logging.getLogger("emails.runner")

TRACK_GROUP = {"roof": "roof", "siding": "siding", "gutters": "gutters",
               "roof_repair": "roof_repair", "siding_repair": "siding_repair"}
FUN_EMAIL_DELAY = timedelta(minutes=60)   # after JobNimbus's instant "Project Update" email
LONG_WAIT_WEEKS = 10
LONG_WAIT_EVERY = 2
JN_NOTE_PREFIX = "[BUILD QUEUE EMAIL]"


def state_mode(mode: str | None = None) -> str:
    return "test" if (mode or email_mode()) == "test" else "live"


def test_cap() -> int:
    """In test mode, cap emails per run so Aaron's inbox isn't flooded."""
    try:
        return int(os.getenv("EMAIL_TEST_MAX_PER_RUN", "20"))
    except ValueError:
        return 20


@dataclass
class Planned:
    job: Job
    ctx: EmailContext | None
    decision: S.Decision
    email: ComposedEmail | None = None
    rep_jn_name: str = ""
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------

class RunContext:
    """Per-run caches so each JobNimbus job is fetched once."""

    def __init__(self, db: Session, now: datetime, mode: str | None = None):
        self.db = db
        self.now = now
        self.mode = mode or email_mode()
        self.smode = state_mode(self.mode)
        self._details: dict[str, JobDetails] = {}
        team.seed_team(db)

    def details(self, job: Job) -> JobDetails:
        if not job.jn_job_id:
            return JobDetails(jnid="")
        if job.jn_job_id not in self._details:
            self._details[job.jn_job_id] = fetch_job_details(job.jn_job_id)
        return self._details[job.jn_job_id]

    def state(self, job: Job) -> EmailState:
        return states_for(self.db, job.id)[self.smode]


def tracked_jobs(db: Session) -> list[Job]:
    return [j for j in db.query(Job).filter(Job.bucket != "archived").all() if S.track_for(j.primary_trade)]


def _queue_order_key(job: Job, state: EmailState):
    # Rescheduled jobs stay at the front; then first in line goes first
    entered = state.entered_queue_at or job.date_entered or job.created_at or datetime.max
    return (0 if state.reschedule_track else 1, entered, job.id)


def jobs_ahead_map(rc: RunContext, jobs: list[Job]) -> dict[int, int]:
    """Builds ahead of each queued job, by time in queue, within the same track."""
    groups: dict[str, list[tuple]] = {}
    for job in jobs:
        st = rc.state(job)
        if not S.in_queue(job, st, rc.now.date()):
            continue
        groups.setdefault(TRACK_GROUP[S.track_for(job.primary_trade)], []).append((_queue_order_key(job, st), job.id))
    ahead = {}
    for members in groups.values():
        for i, (_, job_id) in enumerate(sorted(members)):
            ahead[job_id] = i
    return ahead


def builds_completed_week(db: Session, now: datetime, trade: str) -> int:
    since = now - timedelta(days=7)
    return db.query(JobEvent).filter(JobEvent.created_at >= since, JobEvent.from_bucket == "scheduled",
                                     JobEvent.to_bucket.in_(DONE_BUCKETS), JobEvent.primary_trade == trade).count()


def weather_on(db: Session, now: datetime) -> bool:
    from backend.models.settings import SystemSettings
    row = db.query(SystemSettings).filter(SystemSettings.key == "email_weather_slowdown_date").first()
    return bool(row and row.value and row.value.strip() == now.date().isoformat())


def build_context(rc: RunContext, job: Job, state: EmailState, jobs_ahead: int | None = None) -> tuple[EmailContext, list[str]]:
    d = rc.details(job)
    track = S.track_for(job.primary_trade)
    rep = team.rep_contact(rc.db, job.sales_rep)
    notes = list(d.errors)
    product, flag = research.resolve_product(rc.db, d.materials.shingle_line, job_id=job.id) if track == "roof" else (None, False)
    if flag:
        notes.append(f"unknown shingle product: {d.materials.shingle_line or '(none on material order)'}")
    pm = (team.active_pms(rc.db) or [None])[0]
    ctx = EmailContext(
        job_id=job.id, track=track,
        first_name=d.first_name, customer_name=job.customer_name, customer_email=d.customer_email,
        customer_phone=d.customer_phone, job_address=job.address,
        is_low_slope=d.materials.is_low_slope, is_commercial=d.is_commercial,
        shingle_line=d.materials.shingle_line, product=product, shingle_color=d.materials.shingle_color,
        siding_product=d.materials.siding_product, siding_color=d.materials.siding_color,
        gutter_color=d.materials.gutter_color,
        rep_name=rep["rep_name"], rep_phone=rep["rep_phone"], rep_email=rep["rep_email"],
        pm_name=pm.display_name if pm else "", pm_email=pm.email if pm else "",
        original_date=state.original_date, job_link=d.job_link,
        jobs_ahead=jobs_ahead or 0, jobs_ahead_last_week=state.last_jobs_ahead,
        builds_completed_week=builds_completed_week(rc.db, rc.now, job.primary_trade or ""),
        rescheduled_count=job.rescheduled_count or 0, scheduled_date=d.start_date,
    )
    return ctx, notes


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def _push_jn_note(job: Job, email: ComposedEmail, recipient: str) -> None:
    if not job.jn_job_id:
        return
    try:
        from backend.services.jobnimbus import push_note_to_jn
        text = (f"{JN_NOTE_PREFIX} Sent automated email \"{email.subject}\" to {recipient}.\n\n"
                + email.text)
        push_note_to_jn(job.jn_job_id, text[:9000])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"JobNimbus note failed for job {job.id}: {e}")


def deliver(rc: RunContext, job: Job | None, email: ComposedEmail, to: list[str],
            customer_name: str = "") -> bool:
    ok = send(rc.db, job.id if job else None, email, to, customer_name=customer_name, mode=rc.mode)
    if ok and rc.mode == "live" and email.is_customer and job is not None:
        _push_jn_note(job, email, ", ".join(to))
    return ok


def unsubscribe_url(job: Job) -> str | None:
    from backend.emails.unsubscribe import link_for
    return link_for(job.id)


def _compose(key: str, ctx: EmailContext, state: EmailState | None, job: Job) -> ComposedEmail:
    return compose(key, ctx, rotation_index=(state.rotation_index or 0) if state else 0,
                   unsubscribe_url=unsubscribe_url(job))


# ---------------------------------------------------------------------------
# Weekly
# ---------------------------------------------------------------------------

def plan_weekly(rc: RunContext) -> list[Planned]:
    jobs = tracked_jobs(rc.db)
    ahead = jobs_ahead_map(rc, jobs)
    wx = weather_on(rc.db, rc.now)
    plans = []
    for job in jobs:
        st = rc.state(job)
        S.clear_reschedule_if_dated(st, job, rc.now.date())
        if not S.in_queue(job, st, rc.now.date()):
            continue
        ctx, notes = build_context(rc, job, st, ahead.get(job.id))
        d = S.weekly_decision(ctx, st, job, rc.now, weather_on=wx)
        p = Planned(job, ctx, d, rep_jn_name=job.sales_rep or "", notes=notes)
        if d.template:
            try:
                p.email = _compose(d.template, ctx, st, job)
            except Exception as e:  # noqa: BLE001
                p.decision = S.Decision(None, f"could not build email: {e}")
        plans.append(p)
    rc.db.commit()
    return plans


def _send_planned(rc: RunContext, plans: list[Planned]) -> dict:
    sent = skipped = failed = 0
    cap = test_cap() if rc.mode == "test" else None
    for p in plans:
        if not p.email:
            skipped += 1
            continue
        if cap is not None and sent >= cap:
            skipped += 1
            continue
        ok = deliver(rc, p.job, p.email, [p.ctx.customer_email], customer_name=p.job.customer_name)
        if ok:
            S.apply_sent(rc.state(p.job), p.decision, p.ctx, rc.now)
            sent += 1
        elif rc.mode != "off":
            failed += 1
        else:
            skipped += 1
        rc.db.commit()
    return {"sent": sent, "skipped": skipped, "failed": failed}


def run_weekly(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    rc = RunContext(db, now or datetime.utcnow(), mode)
    return _send_planned(rc, plan_weekly(rc))


def run_welcomes(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    """Same-day Welcome for jobs that just entered the queue (the Thursday run covers Thursdays)."""
    rc = RunContext(db, now or datetime.utcnow(), mode)
    jobs = tracked_jobs(db)
    ahead = jobs_ahead_map(rc, jobs)
    plans = []
    for job in jobs:
        st = rc.state(job)
        if st.welcome_sent or not S.in_queue(job, st, rc.now.date()):
            continue
        ctx, notes = build_context(rc, job, st, ahead.get(job.id))
        d = S.welcome_decision(ctx, st, job, rc.now)
        p = Planned(job, ctx, d, notes=notes)
        if d.template:
            p.email = _compose(d.template, ctx, st, job)
        plans.append(p)
    return _send_planned(rc, plans)


# ---------------------------------------------------------------------------
# Reschedules
# ---------------------------------------------------------------------------

def run_reschedule_checks(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    rc = RunContext(db, now or datetime.utcnow(), mode)
    result = {"customer": 0, "alerts": 0}
    rows = db.query(EmailState).filter(EmailState.mode == rc.smode, EmailState.reschedule_pending_since.isnot(None)).all()
    for st in rows:
        job = db.query(Job).filter(Job.id == st.job_id).first()
        if not job or not S.track_for(job.primary_trade):
            continue
        ctx, _ = build_context(rc, job, st)
        d = S.reschedule_decision(ctx, st, job, rc.now)
        if d.template:
            email = _compose(d.template, ctx, st, job)
            if deliver(rc, job, email, [ctx.customer_email], customer_name=job.customer_name):
                S.apply_sent(st, d, ctx, rc.now)
                result["customer"] += 1
        else:
            st.reschedule_pending_since = None  # nothing for the customer (new date set, or can't email)
        if d.internal_alert:
            to = [ctx.pm_email, ctx.rep_email]
            alert = compose(K.INTERNAL_SECOND_RESCHEDULE, ctx)
            if deliver(rc, job, alert, [a for a in to if a]):
                result["alerts"] += 1
        db.commit()
    return result


# ---------------------------------------------------------------------------
# "You're on the calendar"
# ---------------------------------------------------------------------------

def run_scheduled_emails(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    rc = RunContext(db, now or datetime.utcnow(), mode)
    result = {"sent": 0, "flags": 0}
    rows = db.query(EmailState).filter(EmailState.mode == rc.smode, EmailState.scheduled_seen_at.isnot(None),
                                       EmailState.scheduled_email_sent.is_(False)).all()
    for st in rows:
        if rc.now - st.scheduled_seen_at < FUN_EMAIL_DELAY:
            continue
        job = db.query(Job).filter(Job.id == st.job_id).first()
        if not job or job.bucket != "scheduled" or not S.track_for(job.primary_trade):
            st.scheduled_seen_at = None
            db.commit()
            continue
        ctx, _ = build_context(rc, job, st)
        if st.suppressed or ctx.is_commercial is not False or not ctx.customer_email:
            st.scheduled_email_sent = True  # never eligible; don't keep retrying
            db.commit()
            continue
        try:
            jn_sent = jn_schedule_email_sent(job.jn_job_id, since=st.scheduled_seen_at - timedelta(hours=1)) if job.jn_job_id else False
        except Exception:  # noqa: BLE001
            jn_sent = True  # can't tell: assume it went, so we don't flag the office wrongly
        ctx = replace(ctx, jn_schedule_email_sent=jn_sent)
        if deliver(rc, job, _compose(K.SCHEDULED, ctx, st, job), [ctx.customer_email], customer_name=job.customer_name):
            st.scheduled_email_sent = True
            result["sent"] += 1
            if not jn_sent:
                _office(rc, job, C.JN_EMAIL_MISSING_SUBJECT, C.JN_EMAIL_MISSING_BODY, ctx,
                        date_note=f" (with their date, {K._format_date(ctx.scheduled_date)})" if ctx.scheduled_date else "")
                result["flags"] += 1
        db.commit()
    return result


# ---------------------------------------------------------------------------
# Internal emails
# ---------------------------------------------------------------------------

def _internal(subject: str, body: str) -> ComposedEmail:
    return ComposedEmail("internal", subject, K._wrap_html(markup.to_html(body), None, []),
                         markup.to_text(body), is_customer=False)


def _ops_emails(db: Session) -> list[str]:
    return [r.email for r in db.query(TeamContact).filter(TeamContact.is_active.is_(True),
                                                          TeamContact.role == "ops").all() if r.email]


def _office(rc: RunContext, job: Job, subject_t: str, body_t: str, ctx: EmailContext, **extra) -> None:
    v = {"customer_name": job.customer_name, "job_address": job.address, "job_link": ctx.job_link, **extra}
    to = [office_alert_recipient()] if office_alert_recipient() else team.full_preview_recipients(rc.db)
    deliver(rc, job, _internal(subject_t.format(**v), body_t.format(**v)), to)


def run_long_wait_alerts(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    """Greg (awareness) and the rep (personal touch) at 10 weeks in the queue, then every 2 weeks."""
    rc = RunContext(db, now or datetime.utcnow(), mode)
    result = {"jobs": 0}
    for job in tracked_jobs(db):
        st = rc.state(job)
        if not st.entered_queue_at or not S.in_queue(job, st, rc.now.date()):
            continue
        weeks = (rc.now - st.entered_queue_at).days // 7
        last = st.long_wait_alert_week
        if weeks < LONG_WAIT_WEEKS or (last is not None and weeks < last + LONG_WAIT_EVERY):
            continue
        d = rc.details(job)
        rep = team.rep_contact(db, job.sales_rep)
        v = {"weeks": weeks, "customer_name": job.customer_name, "job_address": job.address,
             "project_word": K.project_word(S.track_for(job.primary_trade)), "job_link": d.job_link,
             "rescheduled_count": job.rescheduled_count or 0, "customer_phone": d.customer_phone or "(not on file)",
             "rep_name": rep["rep_name"], "rep_first": (rep["rep_name"] or "there").split()[0],
             "jn_rep": job.sales_rep or "none listed",
             "rep_label": rep["rep_name"] or "no active rep"}
        v["rep_line"] = (C.LONG_WAIT_OPS_REP_LINE if rep["rep_name"] else C.LONG_WAIT_OPS_NO_REP_LINE).format(**v)
        any_sent = False
        ops = _ops_emails(db)
        if ops:
            any_sent |= deliver(rc, job, _internal(C.LONG_WAIT_OPS_SUBJECT.format(**v), C.LONG_WAIT_OPS_BODY.format(**v)), ops)
        if rep["rep_email"]:
            any_sent |= deliver(rc, job, _internal(C.LONG_WAIT_REP_SUBJECT.format(**v), C.LONG_WAIT_REP_BODY.format(**v)),
                                [rep["rep_email"]])
        if any_sent:
            st.long_wait_alert_week = weeks
            result["jobs"] += 1
        db.commit()
    return result


def run_research(db: Session, now: datetime | None = None, mode: str | None = None, client=None) -> dict:
    rc = RunContext(db, now or datetime.utcnow(), mode)
    rows = research.run_pending_research(db, client=client)
    to = [office_alert_recipient()] if office_alert_recipient() else team.full_preview_recipients(db)
    for row in rows:
        body = research.review_summary(row)
        deliver(rc, None, _internal(C.RESEARCH_SUBJECT.format(product=row.display_name or row.raw_text), body), to)
    return {"researched": len(rows)}


# ---------------------------------------------------------------------------
# Wednesday preview (dry run)
# ---------------------------------------------------------------------------

LABELS = {K.WELCOME: "Welcome", K.ROTATION: "Weekly check-in", K.GETTING_CLOSE: "Getting close",
          K.WEATHER: "Weather slowdown", K.FRONT_OF_LINE: "Front of the line"}


def _label(template: str | None) -> str:
    if not template:
        return "Nothing"
    if template.startswith("week_"):
        return f"Week {template.split('_')[1]}"
    return LABELS.get(template, template.replace("_", " ").title())


def build_preview(db: Session, thursday: datetime | None = None, mode: str | None = None) -> dict:
    """What Thursday's send will do, without sending or changing progress."""
    now = thursday or coming_thursday_10am()
    rc = RunContext(db, now, mode)
    plans = plan_weekly(rc)
    rows = []
    for p in plans:
        rows.append({
            "job_id": p.job.id, "customer": p.job.customer_name, "trade": p.ctx.track if p.ctx else "",
            "rep": p.job.sales_rep or "", "email": p.ctx.customer_email if p.ctx else "",
            "template": p.decision.template, "label": _label(p.decision.template), "reason": p.decision.reason,
            "subject": p.email.subject if p.email else "", "jobs_ahead": p.ctx.jobs_ahead if p.ctx else None,
            "notes": p.notes,
        })
    sending = [r for r in rows if r["template"]]
    fix = [r for r in rows if r["reason"] in ("no customer email", "commercial/residential unknown")]
    long_wait = []
    for job in tracked_jobs(db):
        st = rc.state(job)
        if st.entered_queue_at and S.in_queue(job, st, now.date()):
            weeks = (now - st.entered_queue_at).days // 7
            if weeks >= LONG_WAIT_WEEKS:
                long_wait.append({"customer": job.customer_name, "rep": job.sales_rep or "", "weeks": weeks})
    # Planning never advances anyone's sequence (only a real send does), so nothing to undo
    return {"for": now.isoformat(), "rows": rows, "sending": len(sending), "fix": fix,
            "long_wait": sorted(long_wait, key=lambda r: -r["weeks"])}


def coming_thursday_10am(now: datetime | None = None) -> datetime:
    """The Thursday send that hasn't happened yet: today if it's Thursday before 10:00."""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Indiana/Indianapolis")
    local = (now.replace(tzinfo=timezone.utc) if now else datetime.now(timezone.utc)).astimezone(tz)
    if local.weekday() == 3 and local.hour < 10:
        return local.replace(hour=10, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    return next_thursday_10am(now)


def next_thursday_10am(now: datetime | None = None) -> datetime:
    """Next Thursday 10:00 Indianapolis time, as naive UTC (how times are stored)."""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Indiana/Indianapolis")
    local = (now.replace(tzinfo=timezone.utc) if now else datetime.now(timezone.utc)).astimezone(tz)
    days = (3 - local.weekday()) % 7 or 7
    target = (local + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
    return target.astimezone(timezone.utc).replace(tzinfo=None)


def preview_text(preview: dict, rep_jn_name: str | None = None) -> str:
    rows = preview["rows"] if rep_jn_name is None else [r for r in preview["rows"] if r["rep"] == rep_jn_name]
    lines = []
    going = [r for r in rows if r["template"]]
    skipped = [r for r in rows if not r["template"]]
    lines.append(f"Going out Thursday ({len(going)}):")
    lines += [f"- {r['customer']} ({r['trade']}): {r['label']}" for r in going] or ["- none"]
    if skipped:
        lines.append("")
        lines.append(f"Not getting an email ({len(skipped)}):")
        lines += [f"- {r['customer']}: {r['reason']}" for r in skipped]
    if rep_jn_name is None:
        if preview["fix"]:
            lines.append("")
            lines.append("Please fix in JobNimbus:")
            lines += [f"- {r['customer']}: {r['reason']}" for r in preview["fix"]]
        if preview["long_wait"]:
            lines.append("")
            lines.append("Waiting 10+ weeks:")
            lines += [f"- {r['customer']}: {r['weeks']} weeks ({r['rep'] or 'no rep'})" for r in preview["long_wait"]]
        flagged = [r for r in rows if r["notes"]]
        if flagged:
            lines.append("")
            lines.append("Heads up:")
            lines += [f"- {r['customer']}: {'; '.join(r['notes'])}" for r in flagged]
    return "\n".join(lines)


def send_preview(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    rc = RunContext(db, now or datetime.utcnow(), mode)
    preview = build_preview(db, mode=rc.mode)
    full = team.full_preview_recipients(db)
    body = preview_text(preview)
    deliver(rc, None, _internal(C.PREVIEW_SUBJECT.format(count=preview["sending"]), body), full)
    reps_sent = 0
    for rep in db.query(TeamContact).filter(TeamContact.is_active.is_(True), TeamContact.role == "rep").all():
        mine = [r for r in preview["rows"] if r["rep"] == rep.jn_name]
        if not mine or not rep.email:
            continue
        count = sum(1 for r in mine if r["template"])
        deliver(rc, None, _internal(C.PREVIEW_REP_SUBJECT.format(count=count),
                                    f"Hi {rep.display_name.split()[0]},\n\n" + preview_text(preview, rep.jn_name)), [rep.email])
        reps_sent += 1
    return {"sending": preview["sending"], "reps": reps_sent}


def send_samples(db: Session, now: datetime | None = None, mode: str | None = None) -> dict:
    """Every template for every sample job, to the test recipient only (acceptance check)."""
    from backend.emails.preview import REPAIR_SEQUENCE, SAMPLES, SEQUENCE
    rc = RunContext(db, now or datetime.utcnow(), mode)
    if rc.mode != "test":
        return {"sent": 0, "error": "samples only send in test mode"}
    sent = 0
    for name, ctx in SAMPLES.items():
        for key in (REPAIR_SEQUENCE if K.is_repair(ctx.track) else SEQUENCE):
            email = compose(key, ctx)
            email.subject = f"[{name}] {email.subject}"
            sent += bool(send(db, None, email, ["sample@example.com"], customer_name=ctx.customer_name, mode="test"))
    return {"sent": sent}
