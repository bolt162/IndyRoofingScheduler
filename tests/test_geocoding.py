"""Map spots: the instant quote's address lookup first, JobNimbus's pin only as the backup (no network)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.database import Base
from backend.models.job import Job
from backend.services import geocoding as G
from backend.services import jobnimbus as jn

HOME = (39.7684, -86.1625)          # the Statehouse, 200 W Washington St
JN_PIN = (39.7790, -86.1700)        # JobNimbus's pin, a bit off


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def _lookups(monkeypatch, *answers):
    calls = []

    def make(answer):
        def lookup(address):
            calls.append(address)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return lookup
    monkeypatch.setattr(G, "LOOKUPS", tuple(make(a) for a in answers))
    return calls


def test_the_next_lookup_tries_when_one_misses_is_down_or_lands_outside_indiana(monkeypatch):
    calls = _lookups(monkeypatch, None, RuntimeError("busy"), (41.88, -87.63), HOME)
    assert G.geocode_address("200 W Washington St, Indianapolis, IN, 46204") == HOME
    assert len(calls) == 4


def test_no_address_no_lookup(monkeypatch):
    calls = _lookups(monkeypatch, HOME)
    assert G.geocode_address("  ") is None and calls == []


def test_jobnimbus_zero_pin_is_no_pin():
    m = jn.map_jn_job_to_model({"jnid": "j1", "geo": {"lat": 0, "lon": 0}, "address_line1": "200 W Washington St"})
    assert m["latitude"] is None and m["longitude"] is None


def _sync(db, monkeypatch, address="200 W Washington St", pin=(0, 0)):
    job = {"jnid": "j1", "name": "Test Home - J-10001", "status_name": "Schedule Job", "Trade #1": "Roofing",
           "record_type_name": "Retail", "date_status_change": 1790000000, "address_line1": address,
           "city": "Indianapolis", "state_text": "IN", "zip": "46204", "geo": {"lat": pin[0], "lon": pin[1]}}
    monkeypatch.setattr(jn, "fetch_jobs_at_tracked_statuses", lambda: [job])
    monkeypatch.setattr(jn, "fetch_activities_for_job", lambda jid: [])
    monkeypatch.setattr(jn, "fetch_work_orders_for_job", lambda jid: [])
    import backend.services.note_scanner as ns
    monkeypatch.setattr(ns, "scan_all_unscanned_jobs", lambda db_: {"scanned": 0})
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    jn.sync_jobs_from_jn(db)
    return db.query(Job).one()


def test_a_home_jobnimbus_couldnt_place_gets_on_the_map_and_is_looked_up_once(db, monkeypatch):
    calls = _lookups(monkeypatch, HOME)
    job = _sync(db, monkeypatch)
    assert (job.latitude, job.longitude) == HOME
    _sync(db, monkeypatch)
    assert len(calls) == 1


def test_our_spot_beats_the_jobnimbus_pin_and_a_new_address_is_looked_up_again(db, monkeypatch):
    calls = _lookups(monkeypatch, HOME)
    job = _sync(db, monkeypatch, pin=JN_PIN)
    assert (job.latitude, job.longitude) == HOME
    _sync(db, monkeypatch, pin=JN_PIN)
    assert (job.latitude, job.longitude) == HOME and len(calls) == 1
    _sync(db, monkeypatch, address="202 W Washington St", pin=JN_PIN)
    assert len(calls) == 2


def test_jobnimbus_pin_is_the_backup_and_the_lookup_tries_again_next_sync(db, monkeypatch):
    calls = _lookups(monkeypatch, None)
    job = _sync(db, monkeypatch, pin=JN_PIN)
    assert (job.latitude, job.longitude) == JN_PIN
    _sync(db, monkeypatch, pin=JN_PIN)
    assert len(calls) == 2


def test_lookups_per_sync_are_capped(db, monkeypatch):
    calls = _lookups(monkeypatch, HOME)
    monkeypatch.setattr(jn, "GEOCODE_PER_SYNC", 0)
    job = _sync(db, monkeypatch, pin=JN_PIN)
    assert (job.latitude, job.longitude) == JN_PIN and calls == []
