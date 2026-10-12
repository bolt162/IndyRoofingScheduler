"""No-Build Dates: date ranges the customer asked us not to build (e.g. their wedding)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.main as main
from backend.config import settings
from backend.database import Base, get_db
from backend.models.job import Job
from backend.models.pm import PM
from backend.services import clustering, no_build
from backend.services import weather as weather_service
from backend.services.auth import ClerkUser, get_approved_user
from backend.services.scoring import run_scoring_engine

TODAY = no_build.local_today()


def d(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


def _job(db, name, lat=39.77, lng=-86.16, **kw):
    kw.setdefault("bucket", "to_schedule")
    job = Job(customer_name=name, address=f"{name} St", latitude=lat, longitude=lng,
              primary_trade="roofing", rescheduled_count=0, **kw)
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(main, "SessionLocal", Session)
    # Stay offline: no AI, no Google distances, no forecasts
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setattr(clustering, "get_driving_distances_batch", lambda o, dd: {})
    monkeypatch.setattr(weather_service, "get_forecast", lambda *a, **k: None)

    def db_override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    user = ClerkUser({"sub": "u1", "email": "office@indyroofandrestoration.com", "approved": "true", "admin": "false"})
    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_approved_user] = lambda: user
    yield TestClient(main.app), Session
    main.app.dependency_overrides.clear()


# --- date logic ---

def test_conflict_covers_every_day_of_a_multi_day_build():
    windows = [{"start": d(10), "end": d(12), "reason": "Wedding"}]
    assert no_build.find_conflict(windows, TODAY + timedelta(days=9)) is None
    assert no_build.find_conflict(windows, TODAY + timedelta(days=9), duration_days=2)["reason"] == "Wedding"
    assert no_build.find_conflict(windows, TODAY + timedelta(days=12))
    assert no_build.find_conflict(windows, TODAY + timedelta(days=13)) is None


def test_ended_windows_clear_themselves():
    windows = [{"start": d(-10), "end": d(-1)}, {"start": d(5), "end": d(6)}, {"start": d(0), "end": d(0)}]
    assert [w["start"] for w in no_build.active_windows(windows)] == [d(0), d(5)]


def test_describe():
    assert no_build.describe({"start": "2026-10-20", "end": "2026-10-27", "reason": "Wedding"}) == \
        "Oct 20 to Oct 27 (Wedding)"
    assert no_build.describe({"start": "2026-10-20", "end": "2026-10-20", "reason": None}) == "Oct 20"


# --- API ---

def test_save_list_and_clear(env):
    client, Session = env
    db = Session()
    job_id = _job(db, "Smith").id
    db.close()

    r = client.put(f"/api/jobs/{job_id}/no-build-dates", json={"windows": [
        {"start": d(20), "end": d(27), "reason": " Wedding "},
        {"start": d(3), "end": d(4)},
        {"start": d(-5), "end": d(-2), "reason": "already over"},
    ]})
    assert r.status_code == 200
    body = r.json()
    assert body["no_build_dates"] == [
        {"start": d(3), "end": d(4), "reason": None},
        {"start": d(20), "end": d(27), "reason": "Wedding"},
    ]
    assert body["scheduled_conflict"] is None
    assert client.get(f"/api/jobs/{job_id}").json()["no_build_dates"] == body["no_build_dates"]

    r = client.put(f"/api/jobs/{job_id}/no-build-dates", json={"windows": []})
    assert r.json()["no_build_dates"] == []


def test_end_before_start_is_rejected(env):
    client, Session = env
    db = Session()
    job_id = _job(db, "Smith").id
    db.close()
    r = client.put(f"/api/jobs/{job_id}/no-build-dates",
                   json={"windows": [{"start": d(9), "end": d(8)}]})
    assert r.status_code == 400
    assert "before start date" in r.json()["detail"]


def test_scheduling_inside_window_needs_override(env):
    client, Session = env
    db = Session()
    job_id = _job(db, "Smith", no_build_dates=[{"start": d(10), "end": d(12), "reason": "Wedding"}]).id
    db.close()

    blocked = client.patch(f"/api/jobs/{job_id}", json={"bucket": "scheduled", "date_scheduled": d(11)})
    assert blocked.status_code == 409
    assert "Wedding" in blocked.json()["detail"]

    ok = client.patch(f"/api/jobs/{job_id}", json={"bucket": "scheduled", "date_scheduled": d(13)})
    assert ok.status_code == 200 and ok.json()["date_scheduled"] == d(13)

    moved = client.patch(f"/api/jobs/{job_id}", json={"date_scheduled": d(10), "override_no_build": True})
    assert moved.status_code == 200 and moved.json()["date_scheduled"] == d(10)

    # Editing something else on a job already sitting in the window still works
    assert client.patch(f"/api/jobs/{job_id}", json={"sales_rep": "Greg"}).status_code == 200


def test_adding_window_over_existing_build_warns(env):
    client, Session = env
    db = Session()
    job_id = _job(db, "Smith", bucket="scheduled", date_scheduled=TODAY + timedelta(days=5)).id
    db.close()
    r = client.put(f"/api/jobs/{job_id}/no-build-dates",
                   json={"windows": [{"start": d(4), "end": d(6), "reason": "Wedding"}]})
    assert r.status_code == 200
    assert "already scheduled" in r.json()["scheduled_conflict"]
    assert r.json()["date_scheduled"] == d(5)  # left in place for the office to move


# --- scoring ---

def test_scoring_leaves_out_blocked_jobs_even_must_build(env):
    _, Session = env
    db = Session()
    db.add(PM(name="Pat", baseline_capacity=3, max_capacity=3, is_active=True))
    wedding = [{"start": d(10), "end": d(12), "reason": "Wedding"}]
    blocked = _job(db, "Blocked", no_build_dates=wedding)
    must = _job(db, "MustBuild", lat=39.771, must_build=True, must_build_deadline=TODAY + timedelta(days=11),
                no_build_dates=wedding)
    free = _job(db, "Free", lat=39.772)
    later = _job(db, "Later", lat=39.773, no_build_dates=[{"start": d(30), "end": d(31)}])
    db.commit()

    result = run_scoring_engine(db, target_date=d(11))
    assert {b["job_id"] for b in result["no_build_blocked"]} == {blocked.id, must.id}
    assert result["no_build_blocked_count"] == 2
    assert {r["job_id"] for r in result["recommendations"]} == {free.id, later.id}
    later_rec = next(r for r in result["recommendations"] if r["job_id"] == later.id)
    assert later_rec["no_build_dates"] == [{"start": d(30), "end": d(31), "reason": None}]

    # Blocked jobs don't take a seat in the PM plan
    planned = {j["job_id"] for pm in result["pm_plan"] for j in pm["jobs"]}
    assert planned == {free.id, later.id}
    db.close()


def test_scoring_without_a_date_checks_tomorrow(env):
    _, Session = env
    db = Session()
    tomorrow = _job(db, "BusyTomorrow", no_build_dates=[{"start": d(1), "end": d(1)}])
    next_week = _job(db, "BusyNextWeek", no_build_dates=[{"start": d(7), "end": d(8)}])
    db.commit()
    result = run_scoring_engine(db)
    assert [b["job_id"] for b in result["no_build_blocked"]] == [tomorrow.id]
    assert [r["job_id"] for r in result["recommendations"]] == [next_week.id]
    db.close()
