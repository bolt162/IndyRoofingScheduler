"""Activity log: one row per run/action, totals of outside calls, admin-only, scrubbed, pruned."""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.database as database
import backend.main as main
from backend import activity as A
from backend.activity import ActivityLog
from backend.database import Base, get_db
from backend.services.auth import ClerkUser, get_approved_user, get_current_user


@pytest.fixture
def Session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(database, "SessionLocal", S)
    monkeypatch.setattr(main, "SessionLocal", S)
    return S


def rows(S, **filters):
    db = S()
    try:
        return db.query(ActivityLog).filter_by(**filters).order_by(ActivityLog.id).all()
    finally:
        db.close()


@pytest.fixture
def fake_http(monkeypatch):
    """Install the recorder over a fake httpx.get so nothing touches the network."""
    calls = []

    def fake_get(url, *a, **k):
        calls.append(url)
        status = 500 if "fail" in str(url) else 200
        return SimpleNamespace(status_code=status)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(A, "_installed", False)
    A.install_http_recorder()
    return calls


def test_scrub_hides_secrets():
    s = A.scrub("GET https://maps.googleapis.com/x?address=1+Main&key=AIzaSECRET123 token: abc.def Bearer xyz sk-ant-api03-zzz")
    assert "AIzaSECRET123" not in s and "abc.def" not in s and "xyz" not in s and "sk-ant" not in s
    assert "key=[hidden]" in s


def test_job_run_is_one_row_with_call_totals(Session, fake_http):
    @A.job_run("JobNimbus sync")
    def sync():
        for i in range(118):
            httpx.get(f"https://app.jobnimbus.com/api1/activities?filter=x&n={i}")
        httpx.get("https://maps.googleapis.com/maps/api/geocode/json?key=SECRET")
    sync()
    r = rows(Session)
    assert len(r) == 1
    assert (r[0].kind, r[0].action, r[0].status) == ("job", "JobNimbus sync", "ok")
    assert r[0].detail == "Google Maps 1, JobNimbus 118" and "SECRET" not in r[0].detail


def test_failed_outside_call_gets_its_own_row(Session, fake_http):
    @A.job_run("Morning weather check")
    def check():
        httpx.get("https://api.open-meteo.com/v1/forecast")
        httpx.get("https://api.open-meteo.com/v1/fail")
    check()
    summary = rows(Session, kind="job")[0]
    errors = rows(Session, kind="error")
    assert summary.status == "error" and "Open-Meteo 2 (1 failed)" in summary.detail
    assert len(errors) == 1 and errors[0].source == "open_meteo" and "HTTP 500" in errors[0].detail


def test_job_that_crashes_is_logged_and_still_raises(Session):
    @A.job_run("Secondary trade escalation")
    def boom():
        raise RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        boom()
    r = rows(Session)[0]
    assert r.status == "error" and "RuntimeError: database unavailable" in r.detail


def test_calls_from_worker_threads_count_toward_the_run(Session, fake_http):
    with A.run("job", "scheduler", "Email: weekly"):
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(A.bind_context(lambda i: httpx.get(f"https://app.jobnimbus.com/api1/jobs/{i}")), range(10)))
    r = rows(Session)
    assert len(r) == 1 and r[0].detail == "JobNimbus 10"


def test_claude_and_smtp_calls_are_counted(Session):
    with A.run("job", "scheduler", "Email: research"):
        with A.call("claude", "product research"):
            pass
        with A.call("smtp", "send"):
            pass
    assert rows(Session)[0].detail == "Claude 1, Email 1"


def test_call_outside_any_run_is_a_single_api_row(Session, fake_http):
    httpx.get("https://app.jobnimbus.com/api1/jobs/abcdef0123456789abcdef")
    r = rows(Session)
    assert len(r) == 1 and r[0].kind == "api" and r[0].action == "GET /api1/jobs/{id}"


def test_email_sends_are_logged_one_row_each(Session, monkeypatch):
    from backend.emails import sender
    from backend.emails.compose import compose
    from backend.emails.preview import SAMPLES
    email = compose("welcome", SAMPLES["roof_vista"])
    sender.send(None, 7, email, ["jane@example.com"], customer_name="Jane Smith", mode="off")
    r = rows(Session, kind="email")
    assert len(r) == 1 and r[0].status == "skipped" and r[0].job_id == 7
    assert "to jane@example.com" in r[0].detail and "officially on the build schedule" in r[0].action
    assert "Great news" not in (r[0].detail or "")  # never the body


def test_note_written_to_jobnimbus_is_logged(Session, monkeypatch):
    from backend.services import jobnimbus as jn
    monkeypatch.setattr(jn, "_jn_post", lambda endpoint, body: {"jnid": "n1"})
    jn.push_note_to_jn("jobABC", "[BUILD QUEUE EMAIL] Sent automated email \"Week 3\" to jane@example.com.\n\nbody...")
    r = rows(Session, kind="note")
    assert len(r) == 1 and "JN job jobABC" in r[0].detail and "body..." not in r[0].detail


def test_prune_removes_rows_older_than_90_days(Session):
    db = Session()
    db.add(ActivityLog(kind="job", source="scheduler", action="old", at=datetime.utcnow() - timedelta(days=91)))
    db.add(ActivityLog(kind="job", source="scheduler", action="recent", at=datetime.utcnow() - timedelta(days=5)))
    db.commit()
    db.close()
    assert A.prune() == 1
    assert [r.action for r in rows(Session)] == ["recent"]


# --- API: request logging and admin-only viewing ---

def client_as(Session, email="office@indyroofandrestoration.com", admin=False):
    def db_override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    user = ClerkUser({"sub": "u", "email": email, "approved": "true", "admin": "true" if admin else "false"})

    def approved(request: main.Request):
        request.state.user = user
        run = A.current_run()
        if run is not None:
            run.actor = user.email
        return user
    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_approved_user] = approved
    main.app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(main.app)


@pytest.fixture(autouse=False)
def clear_overrides():
    yield
    main.app.dependency_overrides.clear()


def test_a_change_someone_makes_is_logged_with_who_did_it(Session, clear_overrides):
    c = client_as(Session)
    c.post("/api/emails/weather-slowdown", json={"on": True})
    r = rows(Session, kind="user")
    assert len(r) == 1
    assert r[0].action == "POST /api/emails/weather-slowdown" and r[0].actor == "office@indyroofandrestoration.com"


def test_plain_page_loads_are_not_logged(Session, clear_overrides):
    c = client_as(Session)
    c.get("/api/emails/status")
    assert rows(Session) == []


def test_only_owner_or_admin_can_view_the_log(Session, clear_overrides):
    A.write("job", "scheduler", "JobNimbus sync", detail="JobNimbus 118")
    office = client_as(Session)
    assert office.get("/api/admin/activity").status_code == 403
    owner = client_as(Session, email="aaron@indyroofandrestoration.com")
    data = owner.get("/api/admin/activity").json()
    assert data["rows"][0]["action"] == "JobNimbus sync"
    admin = client_as(Session, email="anjal.parikh@gmail.com", admin=True)
    assert admin.get("/api/admin/activity?q=JobNimbus").status_code == 200
    # Viewing the log doesn't add rows to it
    assert len(rows(Session)) == 1


def test_me_tells_the_frontend_who_can_see_the_log(Session, clear_overrides):
    assert client_as(Session).get("/api/auth/me").json()["owner_or_admin"] is False
    assert client_as(Session, email="aaron@indyroofandrestoration.com").get("/api/auth/me").json()["owner_or_admin"] is True


def test_wiping_the_database_needs_owner_or_admin(Session, clear_overrides):
    office = client_as(Session)
    assert office.post("/api/settings/reset-db").status_code == 403
    denied = rows(Session, kind="user")
    assert denied and denied[-1].status == "error" and "-> 403" in denied[-1].action


def test_log_filters(Session, clear_overrides):
    A.write("email", "smtp", "welcome: Jane", status="ok")
    A.write("error", "jobnimbus", "GET /api1/jobs", status="error", detail="HTTP 500")
    owner = client_as(Session, email="aaron@indyroofandrestoration.com")
    assert [r["kind"] for r in owner.get("/api/admin/activity?status=error").json()["rows"]] == ["error"]
    assert [r["kind"] for r in owner.get("/api/admin/activity?kind=email").json()["rows"]] == ["email"]
