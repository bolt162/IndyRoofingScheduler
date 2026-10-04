"""Recording queue entry, scheduling, finished builds and reschedules from the scheduler."""
from datetime import datetime, date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.emails import events as E
from backend.models.email import EmailState, JobEvent
from backend.models.job import Job
from backend.models.note_log import NoteLog  # noqa: F401  (tables used by sync/notes)

NOW = datetime(2026, 10, 8, 15, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def make_job(db, **kw):
    base = dict(customer_name="Jane Smith", address="123 Main St", bucket="to_schedule",
                jn_status="Schedule Job", primary_trade="roofing", rescheduled_count=0)
    base.update(kw)
    job = Job(**base)
    db.add(job)
    db.commit()
    return job


def states(db, job):
    return {s.mode: s for s in db.query(EmailState).filter_by(job_id=job.id).all()}


def test_job_already_in_queue_uses_jobnimbus_status_change_time(db):
    job = make_job(db)
    when = datetime(2026, 9, 1, 12, 0)
    E.after_sync(db, [(job, "to_schedule", {"date_status_change": when.timestamp() - 0})], now=NOW)
    st = states(db, job)
    assert set(st) == {"test", "live"}
    assert all(abs((s.entered_queue_at - datetime.utcfromtimestamp(when.timestamp())).total_seconds()) < 1
               for s in st.values())


def test_job_moving_into_queue_now_is_stamped_now(db):
    job = make_job(db)
    E.after_sync(db, [(job, "coming_soon", {"date_status_change": 1})], now=NOW)
    assert states(db, job)["live"].entered_queue_at == NOW
    ev = db.query(JobEvent).one()
    assert (ev.from_bucket, ev.to_bucket) == ("coming_soon", "to_schedule")


def test_entered_queue_is_never_overwritten(db):
    job = make_job(db)
    E.after_sync(db, [(job, "coming_soon", {})], now=NOW)
    E.after_sync(db, [(job, "to_schedule", {"date_status_change": 5})], now=NOW + timedelta(days=7))
    assert states(db, job)["live"].entered_queue_at == NOW


def test_newly_scheduled_job_is_marked_for_the_fun_email(db):
    job = make_job(db, bucket="scheduled", jn_status="Pending Start Date")
    E.after_sync(db, [(job, "to_schedule", {})], now=NOW)
    assert states(db, job)["live"].scheduled_seen_at == NOW


def test_finished_build_is_recorded(db):
    job = make_job(db, bucket="primary_completed", jn_status="COC / Punch List")
    E.after_sync(db, [(job, "scheduled", {})], now=NOW)
    ev = db.query(JobEvent).one()
    assert (ev.from_bucket, ev.to_bucket, ev.primary_trade) == ("scheduled", "primary_completed", "roofing")
    assert states(db, job) == {}  # not in queue: no email state needed


def test_reschedule_records_original_date_for_both_modes(db):
    job = make_job(db, bucket="scheduled", date_scheduled=date(2026, 10, 7), rescheduled_count=1)
    E.on_reschedule(db, job, now=NOW)
    for s in states(db, job).values():
        assert s.original_date == date(2026, 10, 7) and s.reschedule_pending_since == NOW


def test_safely_swallows_errors(db):
    def boom(db_):
        raise RuntimeError("email system down")
    assert E.safely(boom, db) is None


def test_real_sync_still_works_when_email_hook_breaks(db, monkeypatch):
    from backend.services import jobnimbus as jn
    jn_job = {"jnid": "j1", "name": "Pat Doe - J-1", "status_name": "Schedule Job", "Trade #1": "Roofing",
              "record_type_name": "Retail", "date_status_change": 1790000000}
    monkeypatch.setattr(jn, "fetch_jobs_at_tracked_statuses", lambda: [jn_job])
    monkeypatch.setattr(jn, "fetch_notes_for_job", lambda jid: [])
    import backend.services.note_scanner as ns
    monkeypatch.setattr(ns, "scan_all_unscanned_jobs", lambda db_: {"scanned": 0})
    monkeypatch.setattr(E, "after_sync", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    result = jn.sync_jobs_from_jn(db)
    assert result["created"] == 1 and not result["errors"]
    assert db.query(Job).one().customer_name == "Pat Doe"


def test_real_sync_records_queue_entry(db, monkeypatch):
    from backend.services import jobnimbus as jn
    jn_job = {"jnid": "j2", "name": "Lee Roe - J-2", "status_name": "Schedule Job", "Trade #1": "Roofing",
              "record_type_name": "Retail", "date_status_change": 1790000000}
    monkeypatch.setattr(jn, "fetch_jobs_at_tracked_statuses", lambda: [jn_job])
    monkeypatch.setattr(jn, "fetch_notes_for_job", lambda jid: [])
    import backend.services.note_scanner as ns
    monkeypatch.setattr(ns, "scan_all_unscanned_jobs", lambda db_: {"scanned": 0})
    jn.sync_jobs_from_jn(db)
    job = db.query(Job).one()
    st = states(db, job)
    assert st["live"].entered_queue_at == datetime.utcfromtimestamp(1790000000)
