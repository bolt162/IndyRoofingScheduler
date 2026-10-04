"""Email controls API, opt-out link, and timer registration."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.main as main
from backend.database import Base, get_db
from backend.emails import runner as R
from backend.emails.jn_data import JobDetails, Materials
from backend.models.email import EmailState
from backend.models.job import Job
from backend.services.auth import ClerkUser, get_admin_user, get_approved_user


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "SessionLocal", Session)

    def db_override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    user = ClerkUser({"sub": "u1", "email": "office@indyroofandrestoration.com", "approved": "true", "admin": "false"})
    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_approved_user] = lambda: user
    monkeypatch.setattr(R, "fetch_job_details", lambda jnid, with_materials=True: JobDetails(
        jnid=jnid, is_commercial=False, first_name="Jane", customer_email="jane@example.com",
        materials=Materials(shingle_line="Owens Corning Oakridge Architectural Shingles", shingle_color="Driftwood")))
    client = TestClient(main.app)
    yield client, Session
    main.app.dependency_overrides.clear()


def add_queued_job(Session):
    db = Session()
    job = Job(customer_name="Jane Smith", address="1 Main St", bucket="to_schedule", jn_status="Schedule Job",
              primary_trade="roofing", sales_rep="Nick Smith", jn_job_id="jn1", rescheduled_count=0)
    db.add(job)
    db.commit()
    for mode in ("test", "live"):
        st = R.S.new_state(job.id, mode)
        st.entered_queue_at = datetime.utcnow() - timedelta(days=20)
        db.add(st)
    db.commit()
    job_id = job.id
    db.close()
    return job_id


def test_status_reports_mode_off_by_default(env, monkeypatch):
    client, _ = env
    monkeypatch.delenv("EMAIL_MODE", raising=False)
    r = client.get("/api/emails/status")
    assert r.status_code == 200 and r.json()["mode"] == "off"


def test_preview_lists_the_job_and_renders_its_email(env):
    client, Session = env
    job_id = add_queued_job(Session)
    p = client.get("/api/emails/preview").json()
    assert p["rows"][0]["customer"] == "Jane Smith" and p["rows"][0]["template"] == "welcome"
    assert "Going out Thursday (1)" in p["text"]
    e = client.get(f"/api/emails/preview/job/{job_id}").json()
    assert e["subject"] == "You're officially on the build schedule, Jane" and "<p" in e["html"]


def test_weather_toggle_sets_coming_thursday_and_clears(env):
    client, _ = env
    on = client.post("/api/emails/weather-slowdown", json={"on": True}).json()
    assert datetime.fromisoformat(on["weather_slowdown_date"]).weekday() == 3
    assert client.post("/api/emails/weather-slowdown", json={"on": False}).json()["weather_slowdown_date"] is None


def test_pause_and_resume_a_customer(env):
    client, Session = env
    job_id = add_queued_job(Session)
    client.post(f"/api/emails/jobs/{job_id}/pause")
    db = Session()
    assert all(s.suppressed for s in db.query(EmailState).filter_by(job_id=job_id))
    assert "office@indyroofandrestoration.com" in db.query(EmailState).filter_by(job_id=job_id).first().suppressed_reason
    db.close()
    assert client.get("/api/emails/preview").json()["rows"][0]["template"] is None
    client.post(f"/api/emails/jobs/{job_id}/resume")
    assert client.get("/api/emails/preview").json()["rows"][0]["template"] == "welcome"


def test_unsubscribe_link_works_only_with_valid_token(env, monkeypatch):
    client, Session = env
    monkeypatch.setenv("EMAIL_UNSUBSCRIBE_SECRET", "s3cret")
    monkeypatch.setenv("EMAIL_PUBLIC_BASE_URL", "https://indyscheduler.top")
    from backend.emails import unsubscribe
    job_id = add_queued_job(Session)
    link = unsubscribe.link_for(job_id)
    assert link.startswith("https://indyscheduler.top/api/email/unsubscribe?job=")
    bad = client.get(f"/api/email/unsubscribe?job={job_id}&t=wrong")
    assert bad.status_code == 400
    ok = client.get(link.replace("https://indyscheduler.top", ""))
    assert ok.status_code == 200 and "unsubscribed" in ok.text
    db = Session()
    assert all(s.suppressed_reason == "unsubscribed" for s in db.query(EmailState).filter_by(job_id=job_id))
    db.close()
    # The office can't accidentally undo a customer's opt-out
    client.post(f"/api/emails/jobs/{job_id}/resume")
    db = Session()
    assert all(s.suppressed for s in db.query(EmailState).filter_by(job_id=job_id))
    db.close()


def test_opt_out_link_works_with_no_setup(env, monkeypatch):
    client, Session = env
    monkeypatch.delenv("EMAIL_UNSUBSCRIBE_SECRET", raising=False)
    monkeypatch.delenv("EMAIL_PUBLIC_BASE_URL", raising=False)
    import backend.database as database
    from backend.emails import unsubscribe
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(unsubscribe, "_cached", None)
    job_id = add_queued_job(Session)
    html = client.get(f"/api/emails/preview/job/{job_id}").json()["html"]
    assert "Stop these weekly updates" in html and "https://indyscheduler.top/api/email/unsubscribe?job=" in html
    link = unsubscribe.link_for(job_id)
    assert client.get(link.replace("https://indyscheduler.top", "")).status_code == 200
    from backend.models.settings import SystemSettings
    db = Session()
    assert len(db.query(SystemSettings).filter_by(key="email_unsubscribe_secret").one().value) == 64
    db.close()


def test_team_list_seeds_and_updates(env):
    client, _ = env
    team = client.get("/api/emails/team").json()
    nick = next(t for t in team if t["jn_name"] == "Nick Smith")
    assert nick["phone"] == "(317) 435-7468"
    nick.update(phone="3175550000")
    r = client.put(f"/api/emails/team/{nick['id']}", json={k: v for k, v in nick.items() if k != "id"}).json()
    assert r["phone"] == "(317) 555-0000"


def test_running_a_send_by_hand_needs_admin(env):
    client, _ = env
    assert client.post("/api/emails/run/weekly").status_code in (401, 403)
    main.app.dependency_overrides[get_admin_user] = lambda: ClerkUser({"approved": "true", "admin": "true"})
    r = client.post("/api/emails/run/preview")
    assert r.status_code == 200 and r.json()["task"] == "preview"
    assert client.post("/api/emails/run/nope").status_code == 404


def test_all_email_timers_are_registered():
    from apscheduler.triggers.cron import CronTrigger

    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def add_job(self, fn, trigger, id, name, misfire_grace_time):
            self.jobs[id] = (fn, str(trigger))
    s = FakeScheduler()
    main._add_email_jobs(s, CronTrigger)
    assert set(s.jobs) == {f"email_{n}" for n in ("run_research", "run_long_wait_alerts", "run_weekly",
                                                   "run_welcomes", "send_preview", "run_reschedule_checks",
                                                   "run_scheduled_emails")}
    assert "day_of_week='thu'" in s.jobs["email_run_weekly"][1] and "hour='10'" in s.jobs["email_run_weekly"][1]
    assert "day_of_week='wed'" in s.jobs["email_send_preview"][1]


def test_timers_do_nothing_when_mode_is_off(monkeypatch):
    monkeypatch.delenv("EMAIL_MODE", raising=False)
    called = []
    monkeypatch.setattr(R, "run_weekly", lambda db: called.append(1))
    main._email_job("run_weekly")()
    assert called == []



def test_samples_only_send_in_test_mode(monkeypatch):
    sent = []
    monkeypatch.setattr(R, "send", lambda db, job_id, email, to, customer_name="", mode=None: sent.append(email.subject) or True)
    monkeypatch.setattr(R.team, "seed_team", lambda db: 0)
    assert R.send_samples(None, mode="live")["sent"] == 0
    result = R.send_samples(None, mode="test")
    assert result["sent"] == len(sent) > 80
    assert any(s.startswith("[low_slope]") for s in sent) and any(s.startswith("[siding_repair]") for s in sent)


@pytest.mark.parametrize("raw,mode", [("test", "test"), ('"test"', "test"), (" Test ", "test"), ("'live'", "live"), ("tset", "off")])
def test_email_mode_tolerates_quotes_and_spaces(monkeypatch, raw, mode):
    from backend.emails.config import email_mode
    monkeypatch.setenv("EMAIL_MODE", raw)
    assert email_mode() == mode


def test_status_shows_what_railway_sent(env, monkeypatch):
    client, _ = env
    monkeypatch.setenv("EMAIL_MODE", "tset")
    s = client.get("/api/emails/status").json()
    assert s["mode"] == "off" and s["mode_setting"] == "tset"
