"""
Push to JobNimbus: book the Weekly Plan's picks in JobNimbus the way Greg does by hand.

Greg's steps (seen on two jobs he booked on 2026-10-19), per job:
  1. On the main trade's work order: start date (all day), the crew and Luke Mroz as subcontractors
     (Luke is also added as an owner of the work order). Save.
  2. Work order status -> Pending Start. This fires JobNimbus's Build Day email right away and the
     "you're on the calendar" text an hour later, so it must happen exactly once, after the date.
  3. Job status -> Pending Start Date, with the same start date and subcontractors.
  4. Note to the rep: "@FirstLast roof scheduled Tuesday 10/27".
  5. Build Block task for the rep, 4:00 to 4:59pm on build day.
  6. Complete the open "Send Work Order & Add Job Date to Job File" and
     "Order Materials & begin trade prep" tasks.

Each step is saved on the job as it finishes (Job.jn_push_steps), so a push that stops halfway picks
up where it left off and never repeats a step, above all the status change that texts the customer.

The app never marks the job scheduled itself. The next JobNimbus sync sees Pending Start Date and the
build queue emails react exactly as they do when Greg books by hand.

JN_BOOKING_MODE: off (default, nothing is written), test (only the jobs in JN_BOOKING_TEST_JOBS),
live (every job the Weekly Plan sends).
"""
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.models.job import Job
from backend.models.pm import PM, Crew

logger = logging.getLogger("jn_booking")

LOCAL_TZ = ZoneInfo("America/Indiana/Indianapolis")
PLANNABLE_BUCKETS = ("to_schedule", "not_built")
BLOCKED_READY = ("flagged", "hold")
WO_PENDING = "pending start"
JOB_PENDING = "pending start date"
BUILD_BLOCK_TYPE = "Build Block"
# Open tasks Greg completes once a build is booked (titles vary in case)
TASKS_TO_COMPLETE = ("send work order & add job date to job file", "order materials & begin trade prep")
# Work orders that are finished or dead are never the one to book
CLOSED_WO_WORDS = ("complete", "cancel", "invoic", "paid", "closed", "lost", "void")
STEPS = ("work_order", "work_order_status", "job_status", "rep_note", "build_block", "tasks")

# The work order that carries each trade's build, best match first
WO_TRADES = {
    "roofing": ["Roofing", "Roof Flat", "Commercial"],
    "roofing_repair": ["Repairs", "Roofing"],
    "siding": ["Siding"],
    "siding_repair": ["Repairs", "Siding"],
    "gutters": ["Gutters"],
    "windows": ["Windows"],
    "paint": ["Exterior Painting"],
    "interior": ["Interior"],
}
# The word the rep note uses for the trade ("roof scheduled Tuesday 10/27")
TRADE_WORD = {"roofing": "roof", "roofing_repair": "repair", "siding": "siding", "siding_repair": "siding repair",
              "gutters": "gutters", "windows": "windows", "paint": "paint", "interior": "interior"}

_push_lock = threading.Lock()
PG_LOCK_KEY = 726_19_2026  # any fixed number; names the Push to JobNimbus lock in Postgres


class BookingError(Exception):
    """A reason the job can't be booked, said plainly for the office."""


def mode() -> str:
    m = (os.getenv("JN_BOOKING_MODE") or "off").strip().lower()
    return m if m in ("off", "test", "live") else "off"


def test_jobs() -> set[str]:
    return {s.strip() for s in (os.getenv("JN_BOOKING_TEST_JOBS") or "").split(",") if s.strip()}


def allowed(job: Job) -> bool:
    m = mode()
    return m == "live" or (m == "test" and (job.jn_job_id or "") in test_jobs())


# --- JobNimbus calls (kept small so tests can swap them out) ---

class JN:
    def get(self, endpoint: str, params: dict | None = None):
        from backend.services.jobnimbus import _jn_get
        return _jn_get(endpoint, params)

    def post(self, endpoint: str, body: dict):
        from backend.services.jobnimbus import _jn_post
        return _jn_post(endpoint, body)

    def put(self, endpoint: str, body: dict):
        from backend.services.jobnimbus import _jn_put
        return _jn_put(endpoint, body)


class Lookups:
    """Things every job in one push needs from JobNimbus, read once."""

    def __init__(self, jn: JN):
        self.jn = jn
        self._statuses = None
        self._settings = None
        self._users = None
        self._subs = None

    def statuses(self) -> dict:
        """{(workflow name lower, status name lower): status id} for jobs and work orders."""
        if self._statuses is None:
            data = self.account_settings()
            out = {}
            for wf in data.get("workflows") or []:
                for s in wf.get("status") or []:
                    out[(wf.get("object_type"), (wf.get("name") or "").lower(), (s.get("name") or "").lower())] = s.get("id")
            self._statuses = out
        return self._statuses

    def account_settings(self) -> dict:
        if self._settings is None:
            self._settings = self.jn.get("account/settings") or {}
        return self._settings

    def task_type_id(self, name: str) -> int | None:
        for t in self.account_settings().get("taskTypes") or []:
            if (t.get("TypeName") or t.get("name") or "").strip().lower() == name.lower():
                return t.get("TaskTypeId") or t.get("TypeId") or t.get("id")
        return None

    def status_id(self, object_type: str, workflow: str, status: str) -> int:
        sid = self.statuses().get((object_type, (workflow or "").lower(), status))
        if sid is None:
            raise BookingError(f"JobNimbus has no \"{status.title()}\" status for {workflow or 'this'} "
                               f"{'work orders' if object_type == 'workorder' else 'jobs'}.")
        return sid

    def users(self) -> list[dict]:
        if self._users is None:
            data = self.jn.get("account/users")
            items = data if isinstance(data, list) else (data or {}).get("users") or (data or {}).get("results") or []
            self._users = [u for u in items if isinstance(u, dict) and u.get("is_active") is not False]
        return self._users

    def user_id(self, name: str) -> str | None:
        want = " ".join((name or "").lower().split())
        for u in self.users():
            full = " ".join(f"{u.get('first_name') or ''} {u.get('last_name') or ''}".lower().split())
            if full == want:
                return u.get("id")
        return None

    def subcontractors(self) -> list[dict]:
        """JobNimbus contacts of type Subcontractor: [{id, name}]."""
        if self._subs is None:
            filt = json.dumps({"must": [{"match": {"record_type_name": "Subcontractor"}}]})
            data = self.jn.get("contacts", {"filter": filt, "size": 1000}) or {}
            self._subs = [{"id": c.get("jnid"), "name": (c.get("display_name") or "").strip()}
                          for c in data.get("results") or [] if c.get("jnid") and c.get("is_active") is not False]
        return self._subs

    def sub_by_name(self, name: str) -> dict | None:
        want = (name or "").strip().lower()
        return next((s for s in self.subcontractors() if s["name"].lower() == want), None)

    def pm_sub(self, pm_name: str) -> dict | None:
        """Our PM as a subcontractor contact ("Luke Mroz - Indy Roof and Restoration")."""
        want = (pm_name or "").strip().lower()
        return next((s for s in self.subcontractors()
                     if s["name"].lower().startswith(want) and "indy roof" in s["name"].lower()), None)


# --- small helpers ---

def local_midnight(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).timestamp())


def local_ts(d: date, hour: int, minute: int = 0) -> int:
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=LOCAL_TZ).timestamp())


def rep_note_text(rep_name: str | None, trade: str | None, d: date) -> str:
    word = TRADE_WORD.get(trade or "", "job")
    when = f"{d:%A} {d.month}/{d.day}"
    mention = f"@{''.join((rep_name or '').split())} " if (rep_name or "").strip() else ""
    return f"{mention}{word} scheduled {when}"


def crew_jn_name(crew: Crew, lookups: Lookups) -> str | None:
    """The crew's subcontractor name in JobNimbus: set in Settings, else matched by the crew's name."""
    if crew.jn_name:
        return crew.jn_name
    base = (crew.name or "").strip().lower()
    if not base:
        return None
    exact = lookups.sub_by_name(crew.name)
    if exact:
        return exact["name"]
    matches = [s["name"] for s in lookups.subcontractors() if s["name"].lower().startswith(base + " - ")]
    crewish = [n for n in matches if "crew" in n.lower()]
    pick = crewish or matches
    return pick[0] if len(pick) == 1 else None


def merge_refs(existing: list | None, add: list[dict]) -> list[dict]:
    out = [dict(x) for x in existing or [] if isinstance(x, dict) and x.get("id")]
    have = {x["id"] for x in out}
    for x in add:
        if x and x.get("id") and x["id"] not in have:
            out.append(x)
            have.add(x["id"])
    return out


def pick_work_order(job: Job, work_orders: list[dict]) -> dict:
    trades = WO_TRADES.get(job.primary_trade or "", [])
    live = [w for w in work_orders or [] if isinstance(w, dict)
            and w.get("is_active") is not False and not w.get("is_archived")]
    live = [w for w in live if not any(x in (w.get("status_name") or "").lower() for x in CLOSED_WO_WORDS)]
    for trade in trades:
        hits = [w for w in live if (w.get("record_type_name") or "").lower() == trade.lower()]
        if len(hits) > 1:
            nums = ", ".join(sorted(w.get("number") or "?" for w in hits))
            raise BookingError(f"This job has more than one open {trade} work order ({nums}). Book it in JobNimbus.")
        if hits:
            return hits[0]
    names = " or ".join(trades) if trades else "a"
    raise BookingError(f"No {names} work order on this job in JobNimbus yet.")


def _list(data, *keys) -> list[dict]:
    if isinstance(data, list):
        return data
    for k in keys:
        if isinstance(data, dict) and isinstance(data.get(k), list):
            return data[k]
    return []


# --- what the Weekly Plan would send ---

def in_progress(job: Job) -> bool:
    """The customer was already told (work order is Pending Start) but later steps didn't finish."""
    steps = job.jn_push_steps or {}
    return bool(steps.get("work_order_status")) and not all(steps.get(s) for s in STEPS)


def candidates(db: Session) -> list[Job]:
    jobs = db.query(Job).filter(Job.planned_date.isnot(None)).order_by(Job.planned_date, Job.customer_name).all()
    return [j for j in jobs if j.bucket in PLANNABLE_BUCKETS or in_progress(j)]


def already_sent(job: Job) -> bool:
    steps = job.jn_push_steps or {}
    return steps.get("date") == (job.planned_date.isoformat() if job.planned_date else None) \
        and all(steps.get(s) for s in STEPS)


def preview_reason(job: Job, db: Session) -> str | None:
    """Why this planned job won't be sent, or None when it's ready to go. Uses only what the app has."""
    if already_sent(job):
        return "Already sent to JobNimbus. It shows as booked after the next sync."
    if in_progress(job):
        # The customer already has the date; only the rep note, Build Block or tasks are left
        return None if allowed(job) else "Sending to JobNimbus is turned off."
    if job.ready_status == "hold":
        return "On hold: the office said not to schedule it yet."
    if job.ready_status == "flagged":
        return "Needs a decision first: the notes say something may stop the build."
    if not job.jn_job_id:
        return "Not a JobNimbus job."
    if not job.planned_crew_id:
        return "Pick a crew first."
    crew = db.get(Crew, job.planned_crew_id)
    if not crew or not crew.is_active:
        return "The crew picked is no longer active. Pick another."
    if not job.planned_pm_id or not db.get(PM, job.planned_pm_id):
        return "Pick a PM first."
    if job.planned_date and job.planned_date < datetime.now(LOCAL_TZ).date():
        return "The planned day has passed. Move it to a new day."
    if not allowed(job):
        return "Sending to JobNimbus is turned off." if mode() == "off" else "Test mode: only the test job is sent."
    return None


def preview(db: Session) -> dict:
    items = []
    for job in candidates(db):
        crew = db.get(Crew, job.planned_crew_id) if job.planned_crew_id else None
        pm = db.get(PM, job.planned_pm_id) if job.planned_pm_id else None
        reason = preview_reason(job, db)
        items.append({"job_id": job.id, "customer_name": job.customer_name, "planned_date": job.planned_date.isoformat(),
                      "crew": crew.name if crew else None, "pm": pm.name if pm else None,
                      "ready": reason is None, "reason": reason})
    return {"mode": mode(), "items": items, "ready_count": sum(1 for i in items if i["ready"])}


# --- the push ---

def _recheck_notes(db: Session, job: Job, jn: JN, ai_client=None) -> None:
    """Notes may have been added since the last scan: read them fresh and rerun the ready check if they changed."""
    from backend.services import jobnimbus as jnapi, ready_check, schedule_sync
    filt = json.dumps({"must": [{"term": {"related.id": job.jn_job_id}}]})
    acts = [a for a in _list(jn.get("activities", {"filter": filt, "size": 200}), "activity") if isinstance(a, dict)]
    wos = schedule_sync.summarize_work_orders(_list(jn.get("v2/workorders", {"filter": filt, "size": 50}),
                                                    "results", "workorders"))
    jn_job = jn.get(f"jobs/{job.jn_job_id}") or {}
    job.jn_work_orders = wos
    job.ready_input = schedule_sync.build_ready_input(jn_job.get("description") or "", acts, wos)
    if ready_check.needs_check(job):
        if not job.ready_input.strip():
            ready_check.apply_result(job, [])
        else:
            blockers = ready_check.ask_ai(job, client=ai_client)
            if blockers is None:
                raise BookingError("Couldn't recheck the notes just now. Try again in a minute.")
            ready_check.apply_result(job, blockers)
    db.commit()
    if job.ready_status in BLOCKED_READY:
        raise BookingError("New notes may stop the build. Answer the ready check first."
                           if job.ready_status == "flagged" else "On hold: the office said not to schedule it yet.")


def _done(db: Session, job: Job, step: str, detail=True) -> None:
    steps = dict(job.jn_push_steps or {})
    steps[step] = detail
    job.jn_push_steps = steps
    db.commit()


def book_job(db: Session, job: Job, who: str, jn: JN | None = None, lookups: Lookups | None = None,
             ai_client=None, recheck: bool = True) -> dict:
    """Do Greg's booking steps for one planned job. Returns {status: booked|skipped|failed, ...}."""
    from backend import activity
    jn = jn or JN()
    lookups = lookups or Lookups(jn)
    d = job.planned_date
    if in_progress(job) and (job.jn_push_steps or {}).get("date"):
        d = date.fromisoformat(job.jn_push_steps["date"])
    try:
        reason = preview_reason(job, db)
        if reason:
            return {"job_id": job.id, "customer_name": job.customer_name, "status": "skipped", "reason": reason}
        # A new day means a new booking: start the steps over
        steps = dict(job.jn_push_steps or {})
        if steps.get("date") != d.isoformat():
            job.jn_push_steps = {"date": d.isoformat(), "by": who}
            db.commit()
        if recheck and not (job.jn_push_steps or {}).get("work_order_status"):
            _recheck_notes(db, job, jn, ai_client)

        crew = db.get(Crew, job.planned_crew_id)
        pm = db.get(PM, job.planned_pm_id)
        crew_name = crew_jn_name(crew, lookups)
        crew_sub = lookups.sub_by_name(crew_name) if crew_name else None
        if not crew_sub:
            raise BookingError(f"Can't find {crew.name} in JobNimbus. Set its JobNimbus name in Settings > Crews.")
        pm_sub = lookups.pm_sub(pm.name)
        if not pm_sub:
            raise BookingError(f"Can't find {pm.name} as a subcontractor in JobNimbus.")
        pm_user = lookups.user_id(pm.name)
        subs = [{"id": crew_sub["id"], "name": crew_sub["name"]}, {"id": pm_sub["id"], "name": pm_sub["name"]}]

        jn_job = jn.get(f"jobs/{job.jn_job_id}") or {}
        filt = json.dumps({"must": [{"term": {"related.id": job.jn_job_id}}]})
        all_wos = [w for w in _list(jn.get("v2/workorders", {"filter": filt, "size": 50}), "results", "workorders")
                   if isinstance(w, dict) and w.get("is_active") is not False and not w.get("is_archived")]
        wo = pick_work_order(job, all_wos)
        wo_id = wo.get("jnid")
        wo_type = wo.get("record_type_name") or ""
        start = local_midnight(d)
        last_day = d + timedelta(days=max(1, job.duration_days or 1) - 1)
        mmddyyyy = lambda x: f"{x.month:02d}/{x.day:02d}/{x.year}"  # noqa: E731
        st = job.jn_push_steps or {}

        if not st.get("work_order_status"):
            wo_pending = (wo.get("status_name") or "").strip().lower() == WO_PENDING
            if wo_pending and st.get("work_order") and wo.get("date_start") == start:
                # Our status change reached JobNimbus but the answer didn't reach us (timeout, restart).
                # The customer already got the text: count it as done, never send it again.
                _done(db, job, "work_order_status", "found already Pending Start")
                st = job.jn_push_steps or {}
            elif wo_pending or any((w.get("status_name") or "").strip().lower() == WO_PENDING for w in all_wos):
                raise BookingError("JobNimbus already has a work order on this job at Pending Start. "
                                   "Someone may have booked it by hand; check JobNimbus before doing anything.")
            elif (jn_job.get("status_name") or "").strip().lower() == JOB_PENDING:
                raise BookingError("This job is already Pending Start Date in JobNimbus. Check it there.")

        if not st.get("work_order"):
            jn.put(f"v2/workorders/{wo_id}", {
                "date_start": start, "all_day": True,
                "all_day_start_date": mmddyyyy(d), "all_day_end_date": mmddyyyy(last_day),
                "subcontractors": merge_refs(wo.get("subcontractors"), subs),
                "owners": merge_refs(wo.get("owners"), [{"id": pm_user}] if pm_user else []),
            })
            _done(db, job, "work_order", wo.get("number") or wo_id)

        if not st.get("work_order_status"):
            # Date is saved first (Greg's SOP), so the Build Day email and text show the right day
            jn.put(f"v2/workorders/{wo_id}", {"status": lookups.status_id("workorder", wo_type, WO_PENDING)})
            _done(db, job, "work_order_status")

        if not st.get("job_status"):
            jn.put(f"jobs/{job.jn_job_id}", {
                "status": lookups.status_id("job", jn_job.get("record_type_name") or "", JOB_PENDING),
                "date_start": start,
                "subcontractors": merge_refs(jn_job.get("subcontractors"), subs),
            })
            _done(db, job, "job_status")

        rep_id, rep_name = jn_job.get("sales_rep"), jn_job.get("sales_rep_name")
        if not st.get("rep_note"):
            from backend.services.jobnimbus import note_body
            jn.post("activities", note_body(job.jn_job_id, rep_note_text(rep_name, job.primary_trade, d)))
            _done(db, job, "rep_note")

        if not st.get("build_block"):
            if rep_id:
                jn.post("tasks", {
                    **({"record_type": tid} if (tid := lookups.task_type_id(BUILD_BLOCK_TYPE)) else {}),
                    "record_type_name": BUILD_BLOCK_TYPE, "title": BUILD_BLOCK_TYPE, "description": "",
                    "date_start": local_ts(d, 16), "date_end": local_ts(d, 16, 59), "all_day": False,
                    "owners": [{"id": rep_id}], "related": [{"id": job.jn_job_id, "type": "job"}],
                })
                _done(db, job, "build_block")
            else:
                _done(db, job, "build_block", "no rep on the job")

        if not st.get("tasks"):
            tasks = _list(jn.get("tasks", {"filter": filt, "size": 200}), "results", "tasks")
            done = 0
            for t in tasks:
                if (not t.get("is_completed") and t.get("is_active") is not False
                        and " ".join((t.get("title") or "").lower().split()) in TASKS_TO_COMPLETE):
                    jn.put(f"tasks/{t['jnid']}", {"is_completed": True})
                    done += 1
            _done(db, job, "tasks", done)

        job.jn_push_error = None
        db.commit()
        activity.write("job", "jobnimbus", "Booked in JobNimbus from the Weekly Plan",
                       detail=f"{job.customer_name}: {d:%a %b %-d}, {crew_sub['name']}, by {who}")
        return {"job_id": job.id, "customer_name": job.customer_name, "status": "booked",
                "work_order": wo.get("number"), "tasks_completed": (job.jn_push_steps or {}).get("tasks")}
    except BookingError as e:
        return _failed(db, job, str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Push to JobNimbus failed for job {job.id}")
        return {**_failed(db, job, f"JobNimbus didn't accept a change ({type(e).__name__}). Nothing after that "
                                   f"step was sent. Push again to finish it."), "jn_error": True}


def _failed(db: Session, job: Job, reason: str) -> dict:
    from backend import activity
    db.rollback()
    job.jn_push_error = reason
    db.commit()
    activity.write("job", "jobnimbus", "Push to JobNimbus stopped", status="error",
                   detail=f"{job.customer_name}: {reason} Steps done: "
                          f"{', '.join(s for s in STEPS if (job.jn_push_steps or {}).get(s)) or 'none'}")
    return {"job_id": job.id, "customer_name": job.customer_name, "status": "failed", "reason": reason}


def push(db: Session, who: str, job_ids: list[int] | None = None, jn: JN | None = None, ai_client=None) -> dict:
    """Book every planned job that's ready (or just job_ids). One push at a time."""
    if not _push_lock.acquire(blocking=False):
        return {"busy": True, "results": []}
    pg = db.get_bind().dialect.name == "postgresql"
    try:
        if pg:
            from sqlalchemy import text
            # Old and new containers overlap during a deploy: one push across all of them
            if not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": PG_LOCK_KEY}).scalar():
                return {"busy": True, "results": []}
        jn = jn or JN()
        lookups = Lookups(jn)
        jobs = candidates(db)
        if job_ids is not None:
            jobs = [j for j in jobs if j.id in set(job_ids)]
        results = []
        for j in jobs:
            results.append(book_job(db, j, who, jn=jn, lookups=lookups, ai_client=ai_client))
            if results[-1].get("jn_error"):
                break  # JobNimbus is struggling: stop instead of hitting it with the rest
        return {"busy": False, "results": results,
                "booked": sum(1 for r in results if r["status"] == "booked"),
                "failed": sum(1 for r in results if r["status"] == "failed")}
    finally:
        if pg:
            try:
                from sqlalchemy import text
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PG_LOCK_KEY})
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
        _push_lock.release()
