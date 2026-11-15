"""/api/health tells the truth: 503 when the background timers are not running or have stopped syncing."""
import time

import pytest
from fastapi.testclient import TestClient

import backend.main as main


class _Sched:
    def __init__(self, running=True):
        self.running = running


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(main._health, "started", time.time())
    monkeypatch.setitem(main._health, "jn_sync_ok", None)
    monkeypatch.setitem(main._health, "sync_minutes", 30)
    return TestClient(main.app)


def _ago(minutes):
    return time.time() - minutes * 60


def test_ok_when_timers_run_and_sync_is_recent(client, monkeypatch):
    monkeypatch.setattr(main.app.state, "scheduler", _Sched(True), raising=False)
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(10))
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["scheduler_running"] is True
    assert body["last_jn_sync_ok"]


def test_503_when_scheduler_never_started(client, monkeypatch):
    monkeypatch.setattr(main.app.state, "scheduler", None, raising=False)
    r = client.get("/api/health")
    assert r.status_code == 503
    assert r.json()["status"] == "down" and r.json()["problems"]


def test_503_when_scheduler_stopped(client, monkeypatch):
    monkeypatch.setattr(main.app.state, "scheduler", _Sched(False), raising=False)
    assert client.get("/api/health").status_code == 503


def test_503_when_sync_stopped_for_hours(client, monkeypatch):
    monkeypatch.setattr(main.app.state, "scheduler", _Sched(True), raising=False)
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(200))
    r = client.get("/api/health")
    assert r.status_code == 503
    assert any("JobNimbus" in p for p in r.json()["problems"])


def test_fresh_start_is_not_stale_before_the_first_sync(client, monkeypatch):
    """A deploy's health check runs right after boot: no sync yet must not fail it."""
    monkeypatch.setattr(main.app.state, "scheduler", _Sched(True), raising=False)
    assert client.get("/api/health").status_code == 200


def test_sync_never_succeeding_since_boot_goes_stale(client, monkeypatch):
    monkeypatch.setattr(main.app.state, "scheduler", _Sched(True), raising=False)
    monkeypatch.setitem(main._health, "started", _ago(200))
    assert client.get("/api/health").status_code == 503


def test_a_good_sync_stamps_the_clock(monkeypatch):
    monkeypatch.setitem(main._health, "jn_sync_ok", None)
    import backend.services.jobnimbus as jn
    monkeypatch.setattr(jn, "sync_jobs_from_jn", lambda db: {"created": 0, "updated": 0, "errors": [], "total_from_jn": 412})
    main._jn_sync_job()
    assert main._health["jn_sync_ok"]


def test_a_failed_sync_does_not_stamp_the_clock(monkeypatch):
    monkeypatch.setitem(main._health, "jn_sync_ok", None)
    import backend.services.jobnimbus as jn

    def boom(db):
        raise RuntimeError("JobNimbus down")
    monkeypatch.setattr(jn, "sync_jobs_from_jn", boom)
    main._jn_sync_job()
    assert main._health["jn_sync_ok"] is None
