"""End-to-end email engine tests. JobNimbus and SMTP are faked; nothing leaves the machine."""
from datetime import datetime, date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.emails import runner as R
from backend.emails.jn_data import JobDetails, Materials
from backend.models.email import EmailState, JobEvent
from backend.models.job import Job
from backend.models.settings import SystemSettings

THU = datetime(2026, 10, 8, 14, 0)  # Thursday 10:00 Eastern, stored as UTC


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


@pytest.fixture
def jn(monkeypatch):
    """Fake JobNimbus: details per jnid, plus whether its scheduling email went out."""
    store = {"details": {}, "jn_email": True, "notes": []}

    def details(jnid, with_materials=True):
        return store["details"].get(jnid) or JobDetails(jnid=jnid)
    monkeypatch.setattr(R, "fetch_job_details", details)
    monkeypatch.setattr(R, "jn_schedule_email_sent", lambda jnid, since=None: store["jn_email"])
    import backend.services.jobnimbus as svc
    monkeypatch.setattr(svc, "push_note_to_jn", lambda jnid, text: store["notes"].append((jnid, text)))
    return store


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(db, job_id, email, to, customer_name="", mode=None):
        if mode == "off":
            return False
        sent.append({"job_id": job_id, "template": email.template, "to": list(to), "subject": email.subject,
                     "mode": mode, "customer": email.is_customer, "text": email.text, "html": email.html})
        return True
    monkeypatch.setattr(R, "send", fake_send)
    return sent


def add_job(db, jn, name, trade="roofing", bucket="to_schedule", jn_status="Schedule Job", entered=None,
            rep="Nick Smith", commercial=False, email=None, shingle="Malarkey Roofing Vista AR 252 Architectural Shingles",
            color="Brilliant Black", **kw):
    job = Job(customer_name=name, address=f"{name} St", bucket=bucket, jn_status=jn_status, primary_trade=trade,
              sales_rep=rep, rescheduled_count=kw.pop("rescheduled_count", 0), jn_job_id=f"jn-{name}", **kw)
    db.add(job)
    db.commit()
    jn["details"][job.jn_job_id] = JobDetails(
        jnid=job.jn_job_id, is_commercial=commercial, first_name=name.split()[0],
        customer_email=email if email is not None else f"{name.split()[0].lower()}@example.com",
        customer_phone="(317) 555-0100", job_link=f"https://app.jobnimbus.com/job/{job.jn_job_id}",
        start_date=date(2026, 10, 21), materials=Materials(shingle_line=shingle, shingle_color=color))
    if entered:
        for mode in ("test", "live"):
            st = R.S.new_state(job.id, mode)
            st.entered_queue_at = entered
            db.add(st)
        db.commit()
    return job


def st(db, job, mode="test"):
    return db.query(EmailState).filter_by(job_id=job.id, mode=mode).one()


# --- Safety switch ---

def test_off_mode_sends_nothing_and_records_no_progress(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    R.run_weekly(db, THU, mode="off")
    assert outbox == []
    assert not st(db, job, "live").welcome_sent


def test_test_mode_progress_never_counts_as_live(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    R.run_weekly(db, THU, mode="test")
    assert [s["template"] for s in outbox] == ["welcome"]
    assert st(db, job, "test").welcome_sent and not st(db, job, "live").welcome_sent
    assert jn["notes"] == []  # test sends are never written to JobNimbus


def test_live_send_is_copied_to_a_jobnimbus_note(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    R.run_weekly(db, THU, mode="live")
    assert outbox[0]["to"] == ["jane@example.com"]
    jnid, text = jn["notes"][0]
    assert jnid == job.jn_job_id and text.startswith("[BUILD QUEUE EMAIL] Sent automated email")


def test_test_mode_cap(db, jn, outbox, monkeypatch):
    monkeypatch.setenv("EMAIL_TEST_MAX_PER_RUN", "2")
    for i in range(5):
        add_job(db, jn, f"Cust{i} Smith", entered=THU - timedelta(days=30 + i))
    R.run_weekly(db, THU, mode="test")
    assert len(outbox) == 2


# --- Weekly sequence and builds ahead ---

def test_weekly_sequence_over_weeks(db, jn, outbox, monkeypatch):
    monkeypatch.setenv("EMAIL_TEST_MAX_PER_RUN", "100")
    for i in range(12):  # a realistic line ahead of her, so she isn't "getting close"
        add_job(db, jn, f"Ahead{i} Owner", entered=THU - timedelta(days=200 - i))
    jane = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    for week in range(4):
        R.run_weekly(db, THU + timedelta(days=7 * week), mode="test")
    assert [s["template"] for s in outbox if s["job_id"] == jane.id] == ["welcome", "week_1", "week_2", "week_3"]


def test_alone_in_line_gets_getting_close_after_welcome(db, jn, outbox):
    jane = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    R.run_weekly(db, THU, mode="test")
    R.run_weekly(db, THU + timedelta(days=7), mode="test")
    assert [s["template"] for s in outbox] == ["welcome", "getting_close"]


def test_jobs_ahead_by_time_in_queue_and_trade(db, jn, outbox):
    jobs = [add_job(db, jn, f"Roof{i} Owner", entered=THU - timedelta(days=200 - i)) for i in range(15)]
    sid = add_job(db, jn, "Sid Owner", trade="siding", entered=THU - timedelta(days=500))
    rc = R.RunContext(db, THU, "test")
    ahead = R.jobs_ahead_map(rc, R.tracked_jobs(db))
    assert ahead[jobs[0].id] == 0 and ahead[jobs[14].id] == 14
    assert ahead[sid.id] == 0  # siding has its own line


def test_rescheduled_job_counts_ahead_of_everyone(db, jn, outbox):
    old = add_job(db, jn, "Old Owner", entered=THU - timedelta(days=300))
    resched = add_job(db, jn, "Resched Owner", entered=THU - timedelta(days=10), rescheduled_count=1)
    st(db, resched).reschedule_track = True
    db.commit()
    ahead = R.jobs_ahead_map(R.RunContext(db, THU, "test"), R.tracked_jobs(db))
    assert ahead[resched.id] == 0 and ahead[old.id] == 1


def test_week2_uses_material_order_product(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=60))
    s = st(db, job)
    s.welcome_sent, s.sequence_week, s.last_jobs_ahead, s.getting_close_sent = True, 1, 0, True
    db.commit()
    R.run_weekly(db, THU, mode="test")
    assert "Malarkey Vista shingles carry a Class 4 impact rating" in outbox[0]["text"]


def test_commercial_never_receives_anything(db, jn, outbox):
    job = add_job(db, jn, "ABC Church", commercial=True, entered=THU - timedelta(days=30))
    R.run_weekly(db, THU, mode="live")
    R.run_welcomes(db, THU, mode="live")
    assert outbox == []


def test_unknown_commercial_flag_blocks(db, jn, outbox):
    add_job(db, jn, "Mystery Owner", commercial=None, entered=THU - timedelta(days=30))
    R.run_weekly(db, THU, mode="live")
    assert outbox == []


def test_weather_slowdown_toggle(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=60))
    s = st(db, job)
    s.welcome_sent, s.sequence_week, s.last_jobs_ahead, s.getting_close_sent = True, 2, 0, True
    db.add(SystemSettings(key="email_weather_slowdown_date", value=THU.date().isoformat()))
    db.commit()
    R.run_weekly(db, THU, mode="test")
    assert outbox[0]["template"] == "weather_slowdown"


# --- Preview matches what actually sends ---

def test_preview_matches_actual_send(db, jn, outbox):
    add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    add_job(db, jn, "ABC Church", commercial=True, entered=THU - timedelta(days=40))
    add_job(db, jn, "Noemail Owner", email="", entered=THU - timedelta(days=50))
    preview = R.build_preview(db, THU, mode="test")
    planned = {r["customer"]: r["template"] for r in preview["rows"]}
    R.run_weekly(db, THU, mode="test")
    actual = {s["job_id"]: s["template"] for s in outbox}
    by_name = {j.customer_name: j.id for j in db.query(Job).all()}
    assert {n: t for n, t in planned.items() if t} == {n: actual[by_name[n]] for n in planned if planned[n]}
    assert planned["ABC Church"] is None and planned["Noemail Owner"] is None
    assert [r["customer"] for r in preview["fix"]] == ["Noemail Owner"]


def test_preview_does_not_advance_progress(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    R.build_preview(db, THU, mode="test")
    R.build_preview(db, THU, mode="test")
    assert not st(db, job).welcome_sent and outbox == []


def test_send_preview_goes_to_full_list_and_reps(db, jn, outbox):
    add_job(db, jn, "Jane Smith", rep="Nick Smith", entered=THU - timedelta(days=30))
    add_job(db, jn, "Bob Jones", rep="Joe Venn", entered=THU - timedelta(days=40))
    R.send_preview(db, THU - timedelta(hours=20), mode="live")
    recipients = [tuple(s["to"]) for s in outbox]
    assert ("aaron@indyroofandrestoration.com", "greg.russell@indyroofandrestoration.com",
            "luke.mroz@indyroofandrestoration.com") in [tuple(sorted(r)) for r in recipients]
    nick = next(s for s in outbox if s["to"] == ["nick.smith@indyroofandrestoration.com"])
    assert "Jane Smith" in nick["text"] and "Bob Jones" not in nick["text"]


# --- Reschedules ---

def resched_setup(db, jn, count):
    job = add_job(db, jn, "Jane Smith", bucket="scheduled", jn_status="Pending Start Date",
                  date_scheduled=date(2026, 10, 7), rescheduled_count=count, entered=THU - timedelta(days=60))
    for mode in ("test", "live"):
        s = st(db, job, mode)
        s.welcome_sent = True
        s.reschedule_count_seen = count - 1
        s.reschedule_track = count > 1
        R.S.note_reschedule(s, job, THU)
    db.commit()
    return job


def test_first_reschedule_sends_customer_email(db, jn, outbox):
    job = resched_setup(db, jn, 1)
    R.run_reschedule_checks(db, THU + timedelta(hours=8), mode="test")
    assert [s["template"] for s in outbox] == ["reschedule"]
    assert "set for Wednesday, October 7" in outbox[0]["text"]
    assert st(db, job).reschedule_track


def test_second_reschedule_alerts_pm_and_rep(db, jn, outbox):
    resched_setup(db, jn, 2)
    R.run_reschedule_checks(db, THU + timedelta(hours=8), mode="live")
    templates = [s["template"] for s in outbox]
    assert templates == ["second_reschedule", "internal_second_reschedule"]
    assert sorted(outbox[1]["to"]) == ["luke.mroz@indyroofandrestoration.com", "nick.smith@indyroofandrestoration.com"]


def test_new_date_same_day_sends_nothing(db, jn, outbox):
    job = resched_setup(db, jn, 1)
    job.date_scheduled = date(2026, 10, 15)
    db.commit()
    R.run_reschedule_checks(db, THU + timedelta(hours=8), mode="test")
    assert outbox == [] and st(db, job).reschedule_pending_since is None


# --- You're on the calendar ---

def sched_job(db, jn):
    job = add_job(db, jn, "Jane Smith", bucket="scheduled", jn_status="Pending Start Date")
    for mode in ("test", "live"):
        s = R.S.new_state(job.id, mode)
        s.scheduled_seen_at = THU
        db.add(s)
    db.commit()
    return job


def test_fun_email_waits_an_hour_after_jobnimbus(db, jn, outbox):
    sched_job(db, jn)
    R.run_scheduled_emails(db, THU + timedelta(minutes=30), mode="test")
    assert outbox == []
    R.run_scheduled_emails(db, THU + timedelta(minutes=61), mode="test")
    assert [s["template"] for s in outbox] == ["scheduled"]
    assert "scheduled for Wednesday, October 21" in outbox[0]["text"]
    assert "more official email" in outbox[0]["text"]
    R.run_scheduled_emails(db, THU + timedelta(hours=5), mode="test")
    assert len(outbox) == 1  # once per job


def test_fun_email_when_jobnimbus_email_missing_flags_office(db, jn, outbox):
    sched_job(db, jn)
    jn["jn_email"] = False
    R.run_scheduled_emails(db, THU + timedelta(hours=2), mode="live")
    assert "more official email" not in outbox[0]["text"]
    assert outbox[1]["subject"].startswith("No scheduling email from JobNimbus")


# --- Long wait alerts ---

def test_long_wait_alerts_at_10_then_every_2_weeks(db, jn, outbox):
    add_job(db, jn, "Jane Smith", entered=THU - timedelta(weeks=10))
    R.run_long_wait_alerts(db, THU, mode="live")
    first = [tuple(s["to"]) for s in outbox]
    assert ("greg.russell@indyroofandrestoration.com",) in first and ("nick.smith@indyroofandrestoration.com",) in first
    R.run_long_wait_alerts(db, THU + timedelta(weeks=1), mode="live")
    assert len(outbox) == 2  # no week 11 alert
    R.run_long_wait_alerts(db, THU + timedelta(weeks=2), mode="live")
    assert len(outbox) == 4  # week 12


def test_long_wait_with_former_rep_tells_greg(db, jn, outbox):
    add_job(db, jn, "Jane Smith", rep="Quincy Barrett", entered=THU - timedelta(weeks=11))
    R.run_long_wait_alerts(db, THU, mode="live")
    assert len(outbox) == 1 and "no longer with us" in outbox[0]["text"]


def test_builds_completed_week_counts_finished_roofs(db, jn):
    for i in range(3):
        db.add(JobEvent(job_id=100 + i, from_bucket="scheduled", to_bucket="primary_completed",
                        primary_trade="roofing", created_at=THU - timedelta(days=2)))
    db.add(JobEvent(job_id=200, from_bucket="scheduled", to_bucket="primary_completed",
                    primary_trade="roofing", created_at=THU - timedelta(days=9)))
    db.commit()
    assert R.builds_completed_week(db, THU, "roofing") == 3


def test_next_thursday_is_10am_indianapolis_year_round():
    assert R.next_thursday_10am(datetime(2026, 10, 5, 12)) == datetime(2026, 10, 8, 14, 0)   # EDT
    assert R.next_thursday_10am(datetime(2026, 12, 7, 12)) == datetime(2026, 12, 10, 15, 0)  # EST


def test_preview_works_when_no_progress_records_exist_yet(db, jn, outbox):
    """Production's first page load: jobs synced, but no email state rows created yet."""
    for i in range(3):
        job = Job(customer_name=f"Fresh{i} Owner", address="x", bucket="to_schedule", jn_status="Schedule Job",
                  primary_trade="roofing", sales_rep="Nick Smith", rescheduled_count=0, jn_job_id=f"jn-fresh{i}")
        db.add(job)
        db.commit()
        jn["details"][job.jn_job_id] = JobDetails(jnid=job.jn_job_id, is_commercial=False, first_name="F",
                                                  customer_email="f@example.com")
    preview = R.build_preview(db, THU, mode="test")
    assert len(preview["rows"]) == 3
    assert db.query(EmailState).count() == 6  # one test + one live row per job, no duplicates


def test_main_contact_gets_the_email_even_when_not_the_customer(db, jn, outbox):
    """Realtors, kids, property managers: the job's main contact is who we email (Aaron)."""
    job = add_job(db, jn, "David Huebner", entered=THU - timedelta(days=30), email="desi@example.com")
    jn["details"][job.jn_job_id].first_name = "Desi"
    jn["details"][job.jn_job_id].contact_name = "Desi Tunny"
    R.run_weekly(db, THU, mode="live")
    assert outbox[0]["to"] == ["desi@example.com"] and "Hi Desi," in outbox[0]["text"]


def test_preview_email_is_one_customer_per_row(db, jn, outbox):
    add_job(db, jn, "Jane Smith", rep="Nick Smith", entered=THU - timedelta(days=30))
    add_job(db, jn, "Bob Jones", rep="Joe Venn", entered=THU - timedelta(days=40))
    R.send_preview(db, THU - timedelta(hours=20), mode="live")
    full = next(s for s in outbox if len(s["to"]) > 1)
    lines = full["text"].splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("Going out Thursday (2)"))
    # Each customer on their own line, alphabetical, with their rep
    assert lines[i + 1].startswith("- Bob Jones") and "Joe Venn" in lines[i + 1]
    assert lines[i + 2].startswith("- Jane Smith") and "Nick Smith" in lines[i + 2]
    assert full["html"].count("<tr>") >= 3  # header + one row per customer
    nick = next(s for s in outbox if s["to"] == ["nick.smith@indyroofandrestoration.com"])
    assert nick["text"].startswith("Hi Nick,") and "Bob Jones" not in nick["text"]


def test_rep_preview_explains_what_customers_read(db, jn, outbox):
    add_job(db, jn, "Jane Smith", rep="Nick Smith", entered=THU - timedelta(days=30))
    R.send_preview(db, THU - timedelta(hours=20), mode="live")
    nick = next(s for s in outbox if s["to"] == ["nick.smith@indyroofandrestoration.com"])
    assert "Nothing for you to send" in nick["text"]
    assert "What your customers are reading" in nick["text"]
    assert "Never give a build date" in nick["text"]
    assert "Their spot" in nick["html"]
    # Short: one line intro, no explainer paragraphs
    assert "This is so you know" not in nick["text"] and "Automatic" not in nick["text"]
    assert "scheduling calls you to set the date" in nick["text"] and "let Greg know" in nick["text"]


def test_corrected_preview_carries_apology_in_one_email(db, jn, outbox):
    add_job(db, jn, "Jane Smith", rep="Nick Smith", entered=THU - timedelta(days=30))
    R.send_corrected_preview(db, THU - timedelta(hours=20), mode="live")
    nick = [s for s in outbox if s["to"] == ["nick.smith@indyroofandrestoration.com"]]
    assert len(nick) == 1 and nick[0]["subject"].startswith("Corrected: ")
    assert nick[0]["text"].startswith("Hi Nick,\n\nA quick apology from Claude")
    assert "Nothing for you to send" in nick[0]["text"]
    full = next(s for s in outbox if len(s["to"]) > 1)
    assert "A quick apology from Claude" in full["text"]


# --- Team emails all use the same readable layout ---

def _team_layout_ok(email: dict) -> None:
    assert "Automatic" not in email["text"], email["subject"]  # no explainer opener
    assert "Jane Smith" in email["text"].split("\n\n")[1], email["subject"]  # leads with the customer
    assert "What to do:" in email["text"], email["subject"]
    assert "Customer: Jane Smith" in email["text"], email["subject"]  # one fact per line
    assert "<table" in email["html"], email["subject"]


def test_every_team_email_explains_itself(db, jn, outbox):
    add_job(db, jn, "Jane Smith", entered=THU - timedelta(weeks=10))
    R.run_long_wait_alerts(db, THU, mode="live")
    for e in outbox:
        _team_layout_ok(e)
    assert any(e["text"].split("\n\n")[0] == "Greg," for e in outbox)
    assert any(e["text"].split("\n\n")[0] == "Hi Nick," for e in outbox)


def test_second_reschedule_and_jn_missing_explain_themselves(db, jn, outbox):
    resched_setup(db, jn, 2)
    R.run_reschedule_checks(db, THU + timedelta(hours=8), mode="live")
    _team_layout_ok(outbox[1])
    assert "already got our apology email" in outbox[1]["text"]


# --- Build date passed but still Pending Start (Jenn Golding J-26426, 2026-10-19) ---

def test_past_date_alert_lists_jobs_whose_date_passed(db, jn, outbox):
    from backend.emails.jn_data import BuildDates
    add_job(db, jn, "Jenn Golding", bucket="scheduled", jn_status="Pending Start Date")
    add_job(db, jn, "Future Fred", bucket="scheduled", jn_status="Pending Start Date")
    dates = {
        "jn-Jenn Golding": BuildDates("J-26426", date(2026, 10, 14), [("WO-11791", "Roofing", date(2026, 10, 14)),
                                                                     ("WO-11792", "Roofing", date(2026, 10, 14))]),
        "jn-Future Fred": BuildDates("J-1", date(2026, 10, 14), [("WO-1", "Roofing", date(2026, 10, 30))]),
    }
    res = R.run_past_date_alerts(db, datetime(2026, 10, 19, 12, 0), mode="live", fetch=lambda jnid: dates[jnid])
    assert res["jobs"] == 1
    mail = outbox[0]
    assert sorted(mail["to"]) == ["greg.russell@indyroofandrestoration.com", "luke.mroz@indyroofandrestoration.com"]
    assert "Jenn Golding (J-26426): Mon Oct 14" not in mail["text"]  # weekday is Wednesday
    assert "Jenn Golding (J-26426): Wed Oct 14, WO-11791, WO-11792 (Roofing)" in mail["text"]
    assert "Future Fred" not in mail["text"]
    assert "What to do:" in mail["text"]


def test_past_date_alert_quiet_when_nothing_passed(db, jn, outbox):
    from backend.emails.jn_data import BuildDates
    add_job(db, jn, "Future Fred", bucket="scheduled", jn_status="Pending Start Date")
    res = R.run_past_date_alerts(db, datetime(2026, 10, 19, 12, 0), mode="live",
                                 fetch=lambda jnid: BuildDates("J-1", date(2026, 10, 30), []))
    assert res == {"jobs": 0} and outbox == []
