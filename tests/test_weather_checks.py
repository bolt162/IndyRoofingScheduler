"""Weather checks look at JobNimbus booking dates, Indianapolis days, and flag instead of pulling."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.job import Job
from backend.models.settings import SystemSettings  # noqa: F401
from backend.models.email import EmailState  # noqa: F401
from backend.services import weather as W
from backend.services import weather_scheduler as WS

TODAY = date(2030, 11, 4)


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(WS, "SessionLocal", Session)
    monkeypatch.setattr(WS, "_today", lambda: TODAY)
    monkeypatch.setattr("backend.activity.write", lambda *a, **k: None)
    s = Session()
    yield s
    s.close()


def booked(db, name, day, **kw):
    j = Job(customer_name=name, address="1 Main", bucket="scheduled", jn_start_date=day,
            latitude=39.7, longitude=-86.1, primary_trade="roofing", material_type="asphalt", **kw)
    db.add(j)
    db.commit()
    return j


def fake_check(calls, status="do_not_build"):
    def check(db, job_id, target, force_bamwx=False):
        calls.append((job_id, target, force_bamwx))
        return {"status": status, "detail": "70% rain"}
    return check


def test_night_before_uses_bam_and_the_jobnimbus_date_and_flags_without_pulling(db, monkeypatch):
    calls = []
    monkeypatch.setattr(WS, "check_weather_for_job", fake_check(calls))
    tomorrow = booked(db, "Tomorrow", date(2030, 11, 5))
    booked(db, "Later", date(2030, 11, 7))
    out = WS.night_before_check()
    assert calls == [(tomorrow.id, "2030-11-05", True)] and out["flagged"] == 1
    db.expire_all()
    j = db.get(Job, tomorrow.id)
    assert j.bucket == "scheduled" and j.weather_status == "do_not_build"   # flagged, still booked


def test_five_am_uses_bam_and_morning_uses_the_free_forecast(db, monkeypatch):
    calls = []
    monkeypatch.setattr(WS, "check_weather_for_job", fake_check(calls, status="good"))
    a = booked(db, "Today", TODAY)
    b = booked(db, "Tomorrow", date(2030, 11, 5))
    WS.five_am_spot_check()
    assert calls == [(a.id, "2030-11-04", True)]
    calls.clear()
    WS.morning_weather_check()
    assert sorted(calls) == sorted([(a.id, "2030-11-04", False), (b.id, "2030-11-05", False)])


def test_free_forecast_by_default_and_bam_only_when_asked(monkeypatch):
    used = []
    monkeypatch.setattr(W.claritywx, "is_configured", lambda: True)
    monkeypatch.setattr(W, "_get_claritywx_forecast", lambda *a: used.append("bam") or {"source": "bam"})
    monkeypatch.setattr(W, "_get_openmeteo_forecast", lambda *a: used.append("free") or {"source": "free"})
    assert W.get_forecast(1, 2, "2030-11-04")["source"] == "free"
    assert W.get_forecast(1, 2, "2030-11-04", provider="bamwx")["source"] == "bam"
    assert used == ["free", "bam"]


def test_bam_without_that_day_falls_back_instead_of_using_another_day(monkeypatch):
    monkeypatch.setattr(W.claritywx, "get_daily_forecast", lambda lat, lon: [{"validAt": "2030-11-04T00:00"}])
    assert W._get_claritywx_forecast(1, 2, "2030-11-09") is None
