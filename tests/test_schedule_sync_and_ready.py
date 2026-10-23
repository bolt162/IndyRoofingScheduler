"""JobNimbus calendar on the Weekly Plan, plans that survive the sync, and the notes ready check."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.main as main
from backend.config import settings
from backend.database import Base, get_db
from backend.models.job import Job
from backend.services import jobnimbus as jn
from backend.services import ready_check as RC
from backend.services import schedule_sync as SS
from backend.services.auth import ClerkUser, get_approved_user

TS_OCT_27 = int(datetime(2026, 10, 27).timestamp())  # midnight local, like JobNimbus all-day dates
TS_OCT_30 = int(datetime(2026, 10, 30).timestamp())
LUKE = {"id": "l", "name": "Luke Mroz - Indy Roof and Restoration"}
AM = {"id": "a", "name": "A&M Home Improvement LLC - Roof Crew"}


def wo(number, trade, status, start=0, subs=(), internal="", customer=""):
    return {"number": number, "record_type_name": trade, "status_name": status, "date_start": start,
            "subcontractors": list(subs), "internal_note": internal, "customer_note": customer, "is_active": True}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


# --- reading the JobNimbus calendar ---

def test_calendar_is_the_earliest_pending_start_work_order_with_its_crew():
    wos = SS.summarize_work_orders([
        wo("WO-2", "Gutters", "New"),
        wo("WO-1", "Roofing", "Pending Start", TS_OCT_27, [AM, LUKE]),
        wo("WO-3", "Siding", "Pending Start", TS_OCT_30, [AM]),
    ])
    start, crews, pm = SS.calendar_from({"date_start": TS_OCT_30}, wos)
    assert start == date(2026, 10, 27)
    assert crews == ["A&M Home Improvement LLC - Roof Crew"] and pm == "Luke Mroz"


def test_calendar_falls_back_to_the_job_start_date():
    start, crews, pm = SS.calendar_from({"date_start": TS_OCT_30, "subcontractors": [LUKE]},
                                        SS.summarize_work_orders([wo("WO-1", "Roofing", "New")]))
    assert start == date(2026, 10, 30) and crews == [] and pm == "Luke Mroz"


def test_ready_input_has_work_order_notes_and_dated_notes_newest_first():
    acts = [
        {"record_type_name": "Note", "note": "Customer still picking a color", "created_by_name": "Nick Smith",
         "date_created": TS_OCT_27},
        {"record_type_name": "Note", "note": "Colors picked: Driftwood", "created_by_name": "Nick Smith",
         "date_created": TS_OCT_30},
        {"record_type_name": "Note", "note": "Scheduling check: OK to schedule.", "date_created": TS_OCT_30},
        {"record_type_name": "Automation", "note": "Build day is coming!", "date_created": TS_OCT_30},
    ]
    wos = SS.summarize_work_orders([wo("WO-9", "Gutters", "New", internal="need colors")])
    text = SS.build_ready_input("Full replacement", acts, wos)
    assert "[Work order WO-9, Gutters, status New] internal note: need colors" in text
    assert text.index("Driftwood") < text.index("still picking")
    assert "Oct 30, 2026 Nick Smith" in text
    assert "Scheduling check" not in text and "Build day" not in text


# --- the sync: JobNimbus wins, plans survive ---

def _sync(db, monkeypatch, status, wos=(), acts=()):
    job = {"jnid": "j1", "name": "Mike Bray - J-26819", "status_name": status, "Trade #1": "Roofing",
           "record_type_name": "Retail", "date_status_change": 1790000000, "date_start": TS_OCT_27}
    monkeypatch.setattr(jn, "fetch_jobs_at_tracked_statuses", lambda: [job])
    monkeypatch.setattr(jn, "fetch_activities_for_job", lambda jid: list(acts))
    monkeypatch.setattr(jn, "fetch_work_orders_for_job", lambda jid: list(wos))
    import backend.services.note_scanner as ns
    monkeypatch.setattr(ns, "scan_all_unscanned_jobs", lambda db_: {"scanned": 0})
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    return jn.sync_jobs_from_jn(db)


def test_a_plan_survives_the_sync_while_the_job_waits(db, monkeypatch):
    _sync(db, monkeypatch, "Schedule Job")
    job = db.query(Job).one()
    job.planned_date, job.planned_pm_id = date(2026, 10, 27), 1
    db.commit()
    _sync(db, monkeypatch, "Schedule Job")
    db.refresh(job)
    assert job.bucket == "to_schedule" and job.planned_date == date(2026, 10, 27)


def test_jobnimbus_booking_replaces_the_plan(db, monkeypatch):
    _sync(db, monkeypatch, "Schedule Job")
    job = db.query(Job).one()
    job.planned_date, job.planned_pm_id = date(2026, 10, 26), 1
    db.commit()
    _sync(db, monkeypatch, "Pending Start Date", wos=[wo("WO-11853", "Roofing", "Pending Start", TS_OCT_27, [AM, LUKE])])
    db.refresh(job)
    assert job.bucket == "scheduled" and job.planned_date is None and job.planned_pm_id is None
    assert job.jn_start_date == date(2026, 10, 27) and job.jn_crews == ["A&M Home Improvement LLC - Roof Crew"]
    assert job.jn_pm == "Luke Mroz" and job.jn_work_orders[0]["number"] == "WO-11853"


def test_sync_stores_the_ready_input(db, monkeypatch):
    _sync(db, monkeypatch, "Schedule Job", wos=[wo("WO-1", "Gutters", "New", internal="need colors")])
    assert "need colors" in db.query(Job).one().ready_input


# --- ready check statuses ---

COLOR = {"issue": "Gutter color not picked yet", "quote": "need colors", "source": "Work order WO-1"}
HOA = {"issue": "Waiting on HOA approval", "quote": "HOA has not approved", "source": "Note by Nick Smith, Oct 19"}


def _job(db, **kw):
    job = Job(customer_name="Pat Doe", address="1 Main St, Indianapolis", bucket="to_schedule",
              primary_trade="roofing", ready_input="notes", jn_job_id="j1", **kw)
    db.add(job)
    db.commit()
    return job


def test_flag_then_ok_stays_ok_until_something_new(db):
    job = _job(db)
    RC.apply_result(job, [COLOR])
    assert job.ready_status == "flagged"
    notes = []
    RC.record_decision(db, job, "ok", "Nikka Samson", "colors are white", push=lambda jid, t: notes.append(t))
    assert job.ready_status == "ok"
    assert notes == ["Scheduling check: OK to schedule. The notes looked like this might hold the job up: "
                     "Gutter color not picked yet. Nikka Samson checked and said it can be scheduled. "
                     "Their note: colors are white"]
    RC.apply_result(job, [COLOR])
    assert job.ready_status == "ok"
    RC.apply_result(job, [COLOR, HOA])
    assert job.ready_status == "flagged"


def test_hold_stays_until_the_notes_settle_it(db):
    job = _job(db)
    RC.apply_result(job, [HOA])
    notes = []
    RC.record_decision(db, job, "hold", "Ross Manlapaz", None, push=lambda jid, t: notes.append(t))
    assert notes == ["Scheduling check: on hold, don't schedule yet. Waiting on: Waiting on HOA approval. "
                     "Set by Ross Manlapaz."]
    RC.apply_result(job, [HOA])
    assert job.ready_status == "hold"
    RC.apply_result(job, [])
    assert job.ready_status == "clear" and job.ready_flags == []


class FakeClaude:
    def __init__(self, reply):
        self.calls = 0
        self.reply = reply
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.reply)])


def test_checks_run_only_when_the_notes_change(db):
    job = _job(db)
    ai = FakeClaude('{"blockers": [{"issue": "Gutter color not picked yet", "quote": "need colors", "source": "WO-1"}]}')
    assert RC.run_ready_checks(db, client=ai)["checked"] == 1
    assert job.ready_status == "flagged" and job.ready_flags[0]["quote"] == "need colors"
    assert RC.run_ready_checks(db, client=ai)["checked"] == 0 and ai.calls == 1
    job.ready_input = "notes\nColors picked: white"
    db.commit()
    ai.reply = '{"blockers": []}'
    RC.run_ready_checks(db, client=ai)
    assert ai.calls == 2 and job.ready_status == "clear"


def test_broken_ai_reply_leaves_the_job_unchecked(db):
    job = _job(db)
    assert RC.run_ready_checks(db, client=FakeClaude("not json"))["failed"] == 1
    assert job.ready_status is None and job.ready_input_hash is None


def test_booked_jobs_are_not_checked(db):
    job = _job(db)
    job.bucket = "scheduled"
    db.commit()
    assert RC.run_ready_checks(db, client=FakeClaude('{"blockers": []}'))["checked"] == 0


# --- morning email ---

def test_morning_email_lists_open_flags_for_office_and_greg(db, monkeypatch):
    from backend.emails import runner as R
    sent = []
    monkeypatch.setattr(R, "send", lambda db_, jid, email, to, customer_name="", mode=None:
                        sent.append({"to": list(to), "subject": email.subject, "text": email.text}) or True)
    assert R.run_ready_digest(db, mode="live") == {"jobs": 0} and sent == []
    a = _job(db, ready_status="flagged", ready_flags=[COLOR])
    b = Job(customer_name="Lee Roe", address="2 Oak Ave", bucket="to_schedule", ready_status="hold",
            ready_flags=[HOA], jn_job_id="j2")
    db.add(b)
    db.commit()
    res = R.run_ready_digest(db, mode="live")
    assert res["jobs"] == 1 and res["on_hold"] == 1
    mail = sent[0]
    assert mail["subject"] == "1 job to check before scheduling"
    assert mail["to"] == ["greg.russell@indyroofandrestoration.com", "nikka.samson@indyroofandrestoration.com",
                          "ross.manlapaz@indyroofandrestoration.com"]
    assert "Pat Doe, 1 Main St\n   What to check: Gutter color not picked yet\n   Status: Needs a decision" in mail["text"]
    assert "Lee Roe, 2 Oak Ave\n   What to check: Waiting on HOA approval\n   Status: On hold" in mail["text"]
    assert "Open the Scheduler\nhttps://indyscheduler.top/plan" in mail["text"]
    assert a.ready_status == "flagged"


def test_morning_email_skips_days_with_only_holds(db, monkeypatch):
    from backend.emails import runner as R
    monkeypatch.setattr(R, "send", lambda *a, **k: pytest.fail("should not send"))
    _job(db, ready_status="hold", ready_flags=[HOA])
    assert R.run_ready_digest(db, mode="live") == {"jobs": 0}


# --- API ---

@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(main, "SessionLocal", Session)

    def db_override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    user = ClerkUser({"sub": "u1", "email": "nikka.samson@indyroofandrestoration.com", "name": "",
                      "approved": "true", "admin": "false"})
    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_approved_user] = lambda: user
    yield TestClient(main.app), Session
    main.app.dependency_overrides.clear()


def test_planning_a_day_keeps_the_job_in_the_queue(client):
    c, Session = client
    s = Session()
    job = Job(customer_name="Pat Doe", address="1 Main St", bucket="to_schedule", primary_trade="roofing")
    s.add(job)
    s.commit()
    r = c.patch(f"/api/jobs/{job.id}", json={"planned_date": "2026-10-27", "planned_pm_id": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["bucket"] == "to_schedule" and body["planned_date"] == "2026-10-27"
    assert body["planned_by"] == "nikka.samson@indyroofandrestoration.com" and body["planned_at"]
    r = c.patch(f"/api/jobs/{job.id}", json={"planned_date": None})
    assert r.json()["planned_date"] is None and r.json()["planned_pm_id"] is None and r.json()["planned_by"] is None


def test_planning_respects_no_build_dates(client):
    c, Session = client
    s = Session()
    job = Job(customer_name="Pat Doe", address="1 Main St", bucket="to_schedule", primary_trade="roofing",
              no_build_dates=[{"start": "2099-10-20", "end": "2099-10-27", "reason": "Wedding"}])
    s.add(job)
    s.commit()
    assert c.patch(f"/api/jobs/{job.id}", json={"planned_date": "2099-10-22"}).status_code == 409
    assert c.patch(f"/api/jobs/{job.id}", json={"planned_date": "2099-10-22", "override_no_build": True}).status_code == 200


def test_answering_a_flag_saves_it_and_notes_jobnimbus(client, monkeypatch):
    c, Session = client
    pushed = []
    monkeypatch.setattr(jn, "push_note_to_jn", lambda jid, text: pushed.append((jid, text)))
    s = Session()
    from backend.emails import team
    team.seed_team(s)
    job = Job(customer_name="Pat Doe", address="1 Main St", bucket="to_schedule", jn_job_id="j1",
              ready_status="flagged", ready_flags=[COLOR])
    s.add(job)
    s.commit()
    assert [j["id"] for j in c.get("/api/jobs/ready/open").json()] == [job.id]
    assert c.post(f"/api/jobs/{job.id}/ready-decision", json={"decision": "maybe"}).status_code == 422
    r = c.post(f"/api/jobs/{job.id}/ready-decision", json={"decision": "ok", "note": "white"})
    assert r.status_code == 200 and r.json()["job"]["ready_status"] == "ok" and r.json()["pushed_to_jn"]
    assert pushed[0][0] == "j1" and "Nikka Samson checked" in pushed[0][1]
    assert c.get("/api/jobs/ready/open").json() == []
