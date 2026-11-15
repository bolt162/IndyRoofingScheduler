"""Settings can't break the timers, and the opt-out signing secret never leaves the server."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
import backend.main as main
from backend.database import Base, get_db
from backend.models.settings import SystemSettings
from backend.services.auth import ClerkUser, get_approved_user, get_current_user


@pytest.fixture
def Session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "SessionLocal", S)
    monkeypatch.setattr(main, "SessionLocal", S)
    db = S()
    for key, value in [("weather_morning_check_time", "06:00"), ("bamwx_check_time", "20:00"),
                       ("jn_sync_interval_minutes", "15"), ("pm_baseline_capacity", "3"),
                       ("email_unsubscribe_secret", "the-real-signing-secret")]:
        db.add(SystemSettings(key=key, value=value, description=""))
    db.commit()
    db.close()
    return S


@pytest.fixture
def client(Session):
    def db_override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    user = ClerkUser({"sub": "u", "email": "office@example.com", "approved": "true", "admin": "false"})

    def approved(request: main.Request):
        request.state.user = user
        return user
    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_approved_user] = approved
    main.app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def value(Session, key):
    db = Session()
    try:
        return db.query(SystemSettings).filter(SystemSettings.key == key).first().value
    finally:
        db.close()


# --- SCH-07: the opt-out signing secret ---

def test_settings_list_never_includes_the_opt_out_secret(client):
    r = client.get("/api/settings/")
    assert r.status_code == 200
    assert "email_unsubscribe_secret" not in r.json()
    assert "the-real-signing-secret" not in r.text
    assert r.json()["pm_baseline_capacity"]["value"] == "3"


def test_the_opt_out_secret_cannot_be_changed_from_the_app(client, Session):
    r = client.put("/api/settings/email_unsubscribe_secret", json={"value": "attacker"})
    assert r.status_code == 403
    assert "attacker" not in r.text and "the-real-signing-secret" not in r.text
    assert value(Session, "email_unsubscribe_secret") == "the-real-signing-secret"


# --- SCH-04: timer settings are checked on save ---

@pytest.mark.parametrize("key,bad", [
    ("weather_morning_check_time", "6am"),
    ("weather_morning_check_time", "6:00 AM"),
    ("weather_morning_check_time", ""),
    ("weather_morning_check_time", "25:00"),
    ("bamwx_check_time", "20:60"),
    ("jn_sync_interval_minutes", "abc"),
    ("jn_sync_interval_minutes", "0"),
    ("jn_sync_interval_minutes", "-5"),
    ("jn_sync_interval_minutes", "1.5"),
])
def test_a_bad_timer_setting_is_refused_and_not_saved(client, Session, key, bad):
    before = value(Session, key)
    r = client.put(f"/api/settings/{key}", json={"value": bad})
    assert r.status_code == 400
    assert r.json()["detail"]  # a plain sentence the page can show
    assert value(Session, key) == before


@pytest.mark.parametrize("key,good,saved", [
    ("weather_morning_check_time", "06:30", "06:30"),
    ("weather_morning_check_time", "6:30", "06:30"),
    ("bamwx_check_time", " 19:45 ", "19:45"),
    ("jn_sync_interval_minutes", "20", "20"),
])
def test_a_good_timer_setting_is_saved(client, Session, key, good, saved):
    r = client.put(f"/api/settings/{key}", json={"value": good})
    assert r.status_code == 200
    assert value(Session, key) == saved


def test_other_settings_still_save_as_before(client, Session):
    r = client.put("/api/settings/pm_baseline_capacity", json={"value": "4"})
    assert r.status_code == 200
    assert value(Session, "pm_baseline_capacity") == "4"


# --- SCH-04: a bad value already in the database falls back, it never stops every timer ---

def test_timer_settings_fall_back_per_field(Session):
    db = Session()
    db.query(SystemSettings).filter(SystemSettings.key == "weather_morning_check_time").first().value = "6am"
    db.query(SystemSettings).filter(SystemSettings.key == "jn_sync_interval_minutes").first().value = "soon"
    db.commit()
    morning, night, sync = main._timer_settings(db)
    db.close()
    assert morning == (6, 0)       # default, because "6am" is not HH:MM
    assert night == (20, 0)        # the saved good value
    assert sync == 30              # default, because "soon" is not a number


def test_timer_settings_use_saved_good_values(Session):
    db = Session()
    db.query(SystemSettings).filter(SystemSettings.key == "weather_morning_check_time").first().value = "05:45"
    db.commit()
    assert main._timer_settings(db) == ((5, 45), (20, 0), 15)
    db.close()


def test_timers_start_even_with_a_bad_saved_time(Session, monkeypatch):
    db = Session()
    db.query(SystemSettings).filter(SystemSettings.key == "bamwx_check_time").first().value = ""
    db.commit()
    db.close()
    monkeypatch.setattr(main, "_resume_email_retries", lambda scheduler: None)

    async def start_and_look():
        sched = main._start_scheduler()
        try:
            assert sched is not None
            job = sched.get_job("night_before_weather")
            assert job is not None and "hour='20'" in str(job.trigger)
            assert sched.get_job("jn_sync_watch") is not None
        finally:
            if sched is not None:
                sched.shutdown(wait=False)
    asyncio.run(start_and_look())
