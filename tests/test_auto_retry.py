"""A failed send tries again by itself about 30 minutes later, never double-sends, and never spams Aaron.
Nothing leaves the machine; the clock is always passed in."""
from datetime import date, datetime, timedelta

import pytest

from backend import main
from backend.emails import abc, retry
from backend.emails import runner as R
from backend.models.email import EmailLog, TeamContact
from backend.models.job import Job
from backend.services import weather_scheduler as WS
from tests.test_email_runner import THU, _flaky_send, _three_queued, add_job, db, jn, outbox  # noqa: F401
from tests.test_staff_email_readability import assert_readable

AARON = ["aaron@indyroofandrestoration.com"]
LATER = THU + timedelta(minutes=30)      # 10:30 AM Indianapolis
LAST = THU + timedelta(minutes=60)       # 11:00 AM


def factory(db):
    """fire() opens its own session; in tests that is the test's session, kept open."""
    class Keep:
        def __call__(self):
            return self
        def __getattr__(self, name):
            return getattr(db, name)
        def close(self):
            pass
    return Keep()


def alerts(outbox):
    return [m for m in outbox if m["to"] == AARON]


def customers(outbox):
    return sorted(m["to"][0] for m in outbox if m["customer"])


def saved(db, run="weekly", mode="live"):
    return retry.load(db, run, mode, THU)


class FakeScheduler:
    def __init__(self):
        self.jobs = {}

    def add_job(self, fn, trigger, **kw):
        self.jobs[kw["id"]] = (fn, trigger, kw)

    def remove_job(self, id):
        self.jobs.pop(id)


@pytest.fixture(autouse=True)
def no_scheduler():
    retry.set_scheduler(None)
    yield
    retry.set_scheduler(None)


# --- Weekly ---

def test_first_failure_says_it_will_try_again_automatically_and_saves_the_retry(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    res = R.run_weekly(db, THU, mode="live")
    assert res["failed"] == 1
    [mail] = alerts(outbox)
    assert mail["subject"] == "Thursday customer emails: 1 customer did not get their email"
    assert "The Scheduler will try again by itself at 10:30 AM" in mail["text"]
    assert "ask Claude" not in mail["text"]
    assert_readable(mail)
    data = saved(db)
    assert data["done"] == 0 and datetime.fromisoformat(data["due"]) == LATER


def test_the_retry_sends_only_to_the_customer_who_missed_out_and_is_quiet_when_it_works(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    assert customers(outbox) == ["amy@example.com", "cal@example.com"]
    _flaky_send(monkeypatch, outbox)   # the mail problem cleared up
    out = retry.fire("weekly", now=LATER, mode="live", session_factory=factory(db))
    assert out["ran"] and out["result"]["sent"] == 1 and out["result"]["failed"] == 0
    assert customers(outbox) == ["amy@example.com", "bob@example.com", "cal@example.com"]   # nobody twice
    assert len(alerts(outbox)) == 1                                                          # no second alert
    assert saved(db)["due"] is None                                                          # nothing left waiting
    assert retry.fire("weekly", now=LATER + timedelta(minutes=1), mode="live", session_factory=factory(db)) == {"ran": False}


def test_a_retry_that_is_not_due_yet_does_nothing(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    _flaky_send(monkeypatch, outbox)
    assert retry.fire("weekly", now=THU + timedelta(minutes=10), mode="live", session_factory=factory(db)) == {"ran": False}
    assert customers(outbox) == ["amy@example.com", "cal@example.com"]


def test_two_retries_then_one_final_alert_and_nothing_more(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    assert len(alerts(outbox)) == 1
    first = retry.fire("weekly", now=LATER, mode="live", session_factory=factory(db))
    assert first["result"]["failed"] == 1
    assert len(alerts(outbox)) == 1                       # the middle attempt stays quiet
    assert datetime.fromisoformat(saved(db)["due"]) == LAST   # and the second retry is lined up
    second = retry.fire("weekly", now=LAST, mode="live", session_factory=factory(db))
    assert second["result"]["failed"] == 1
    [first_alert, final] = alerts(outbox)
    assert final["subject"] == "Thursday customer emails: 1 customer still did not get their email"
    assert "tried twice more" in final["text"] and "ask Claude to run it again" in final["text"]
    assert "Bob Owner" in final["text"] and "Amy" not in final["text"]
    assert_readable(final)
    assert saved(db)["due"] is None
    after = retry.fire("weekly", now=LAST + timedelta(minutes=30), mode="live", session_factory=factory(db))
    assert after == {"ran": False}                        # at most 2 retries a day
    assert len(alerts(outbox)) == 2
    assert customers(outbox) == ["amy@example.com", "cal@example.com"]


def test_a_run_that_crashes_tells_aaron_when_it_retries_and_the_retry_finishes_the_job(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, explode_to=["cal@example.com"])
    real = R._send_planned

    def dies(rc, plans):
        real(rc, plans)
        raise RuntimeError("deploy killed the process")
    monkeypatch.setattr(R, "_send_planned", dies)
    with pytest.raises(RuntimeError):
        R.run_weekly(db, THU, mode="live")
    [mail] = alerts(outbox)
    assert mail["subject"] == "Thursday customer emails stopped before it finished"
    assert "try again by itself at 10:30 AM" in mail["text"] and "will not get a second one" in mail["text"]
    monkeypatch.setattr(R, "_send_planned", real)
    _flaky_send(monkeypatch, outbox)
    out = retry.fire("weekly", now=LATER, mode="live", session_factory=factory(db))
    assert out["result"]["failed"] == 0
    assert customers(outbox) == ["amy@example.com", "bob@example.com", "cal@example.com"]   # each exactly once
    assert len(alerts(outbox)) == 1


def test_a_crash_that_keeps_happening_ends_with_one_final_alert(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox)
    monkeypatch.setattr(R, "plan_weekly", lambda rc: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        R.run_weekly(db, THU, mode="live")
    retry.fire("weekly", now=LATER, mode="live", session_factory=factory(db))
    retry.fire("weekly", now=LAST, mode="live", session_factory=factory(db))
    subjects = [m["subject"] for m in alerts(outbox)]
    assert subjects == ["Thursday customer emails stopped before it finished",
                        "Thursday customer emails still did not finish"]
    assert "ask Claude" in alerts(outbox)[1]["text"]
    assert all("boom" not in m["text"] for m in alerts(outbox))


def test_a_clean_run_clears_a_retry_that_was_waiting(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    assert saved(db)["due"]
    _flaky_send(monkeypatch, outbox)
    R.run_weekly(db, THU + timedelta(minutes=5), mode="live")    # Aaron asked Claude to run it by hand
    assert saved(db)["due"] is None
    assert retry.fire("weekly", now=LATER, mode="live", session_factory=factory(db)) == {"ran": False}


def test_off_mode_never_retries_or_alerts(db, jn, outbox, monkeypatch):
    plan = retry.after_failure(db, "weekly", THU, "off")
    assert plan.retry_at is None and not plan.final
    assert saved(db, mode="off") == {}
    assert retry.fire("weekly", now=LATER, mode="off", session_factory=factory(db)) == {"ran": False}


def test_test_mode_retries_are_kept_apart_from_live_ones(db, jn, outbox):
    retry.after_failure(db, "weekly", THU, "test")
    assert saved(db, mode="test")["due"] and saved(db, mode="live") == {}


# --- Welcome ---

def test_welcome_failures_retry_and_send_only_to_the_one_who_missed_out(db, jn, outbox, monkeypatch):
    add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=1))
    add_job(db, jn, "Kim Lee", entered=THU - timedelta(days=1))
    _flaky_send(monkeypatch, outbox, bad_to=["jane@example.com"])
    res = R.run_welcomes(db, THU, mode="live")
    assert res["failed"] == 1 and customers(outbox) == ["kim@example.com"]
    [mail] = alerts(outbox)
    assert mail["subject"] == "Welcome emails: 1 customer did not get their email"
    assert "try again by itself at 10:30 AM" in mail["text"]
    _flaky_send(monkeypatch, outbox)
    out = retry.fire("welcomes", now=LATER, mode="live", session_factory=factory(db))
    assert out["result"]["sent"] == 1
    assert customers(outbox) == ["jane@example.com", "kim@example.com"]
    assert saved(db, "welcomes")["due"] is None


def test_a_welcome_run_that_crashes_now_tells_aaron_and_retries(db, jn, outbox, monkeypatch):
    add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=1))
    _flaky_send(monkeypatch, outbox)
    real = R.jobs_ahead_map
    monkeypatch.setattr(R, "jobs_ahead_map", lambda rc, jobs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        R.run_welcomes(db, THU, mode="live")
    [mail] = alerts(outbox)
    assert mail["subject"] == "Welcome emails stopped before it finished" and "10:30 AM" in mail["text"]
    monkeypatch.setattr(R, "jobs_ahead_map", real)
    _flaky_send(monkeypatch, outbox)
    retry.fire("welcomes", now=LATER, mode="live", session_factory=factory(db))
    assert customers(outbox) == ["jane@example.com"]


# --- Saved across a restart ---

def test_a_restart_inside_the_30_minutes_still_runs_the_retry_at_its_time(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    fake = FakeScheduler()
    retry.set_scheduler(fake)
    assert retry.resume(db, THU + timedelta(minutes=12), "live") == [("weekly", LATER)]   # still waits for 10:30
    fn, trigger, kw = fake.jobs["email_retry_weekly"]
    assert fn is retry.fire and trigger == "date" and kw["args"] == ["weekly"]
    assert kw["run_date"].replace(tzinfo=None) == LATER


def test_a_retry_that_came_due_while_the_app_was_down_runs_soon_after_start(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    fake = FakeScheduler()
    retry.set_scheduler(fake)
    start = THU + timedelta(minutes=45)
    assert retry.resume(db, start, "live") == [("weekly", start + retry.RESUME_DELAY)]
    _flaky_send(monkeypatch, outbox)
    out = retry.fire("weekly", now=start + retry.RESUME_DELAY, mode="live", session_factory=factory(db))
    assert out["ran"] and customers(outbox)[1] == "bob@example.com"
    assert len(customers(outbox)) == 3


def test_a_retry_from_an_earlier_day_is_dropped(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    tomorrow = THU + timedelta(days=1)
    assert retry.resume(db, tomorrow, "live") == []
    _flaky_send(monkeypatch, outbox)
    assert retry.fire("weekly", now=tomorrow, mode="live", session_factory=factory(db)) == {"ran": False}
    assert customers(outbox) == ["amy@example.com", "cal@example.com"]


def test_startup_resumes_waiting_retries(db, jn, outbox, monkeypatch):
    called = []
    fake = FakeScheduler()
    monkeypatch.setattr(main, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(retry, "resume", lambda d: called.append(d) or [("weekly", THU)])
    main._resume_email_retries(fake)
    assert called == [db] and retry._scheduler is fake


def test_a_retry_that_is_already_running_is_not_started_twice(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    status, data = retry.begin(db, "weekly", LATER, "live")
    assert status == "go" and data["done"] == 1
    assert retry.begin(db, "weekly", LATER + timedelta(minutes=2), "live")[0] == "none"      # still running
    assert retry.begin(db, "weekly", LATER + timedelta(minutes=16), "live")[0] == "go"       # that one died


def test_a_retry_waits_for_a_thursday_run_that_is_still_going(db, jn, outbox, monkeypatch):
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    R._put_setting(db, "email_weekly_started_live", (LATER - timedelta(minutes=2)).isoformat(), "x")
    R._put_setting(db, "email_weekly_done_live", "2026-10-07", "x")   # not finished today
    fake = FakeScheduler()
    retry.set_scheduler(fake)
    _flaky_send(monkeypatch, outbox)
    assert retry.fire("weekly", now=LATER, mode="live", session_factory=factory(db)) == {"ran": False}
    assert customers(outbox) == ["amy@example.com", "cal@example.com"]
    assert kw_run_date(fake) == LATER + retry.RESUME_DELAY


def kw_run_date(fake):
    return fake.jobs["email_retry_weekly"][2]["run_date"].replace(tzinfo=None)


# --- ABC daily ---

ABC_NOW = datetime(2026, 11, 9, 17, 0)   # Monday noon Indianapolis


@pytest.fixture
def abc_db(db):
    db.add_all([TeamContact(jn_name="Luke Mroz", display_name="Luke Mroz", role="pm", email="l@x.com", phone="3170000001"),
                TeamContact(jn_name="Greg Russell", display_name="Greg Russell", role="ops", email="g@x.com", phone="3170000002")])
    db.commit()
    return db


def _abc_delivery():
    return {"jn_job_id": "a", "job_number": "J-1", "customer": "Pat Smith", "address": "1 Main St, Zionsville",
            "abc_order": "C12-1", "day": date(2026, 11, 10)}


def _abc_mail(monkeypatch, outbox, ok=lambda to, email: True):
    def send(db, job_id, email, to, customer_name="", mode=None):
        good = ok(to, email)
        db.add(EmailLog(job_id=job_id, template=email.template, recipient=",".join(to), subject=email.subject, mode=mode,
                        result="sent" if good else "failed", detail=None if good else "smtp down", created_at=ABC_NOW))
        db.commit()
        if good:
            outbox.append({"template": email.template, "to": list(to), "subject": email.subject, "text": email.text,
                           "customer": False})
        return good
    monkeypatch.setattr(abc, "send", send)
    monkeypatch.setattr(R, "send", send)


def _abc_is_daily(to, email):
    return email.template != abc.DAILY


def test_abc_reminder_that_fails_to_send_retries_and_only_sends_once(abc_db, outbox, monkeypatch):
    db = abc_db
    _abc_mail(monkeypatch, outbox, ok=_abc_is_daily)   # ABC's mail is refused; internal notes get through
    r = abc.run_abc_daily(db, now=ABC_NOW, mode="live", fetch=lambda d: [_abc_delivery()])
    assert r["sent"] is False
    [aaron] = alerts(outbox)
    assert "try again by itself at 12:30 PM" in aaron["text"]
    [ops] = [m for m in outbox if set(m["to"]) == {"g@x.com", "l@x.com"}]
    assert ops["subject"] == "The ABC delivery reminder is running late" and "12:30 PM" in ops["text"]
    assert "please don't send it yourself" in ops["text"]
    assert_readable(ops)
    monkeypatch.setattr(abc, "fetch_deliveries", lambda d: [_abc_delivery()])
    monkeypatch.setattr(abc, "fetch_job_orders", lambda j: [])
    _abc_mail(monkeypatch, outbox)   # mail works again
    out = retry.fire("abc_daily", now=ABC_NOW + timedelta(minutes=30), mode="live", session_factory=factory(db))
    assert out["result"]["sent"] is True
    assert len([m for m in outbox if m["template"] == abc.DAILY]) == 1       # ABC got exactly one email
    assert retry.fire("abc_daily", now=ABC_NOW + timedelta(minutes=31), mode="live", session_factory=factory(db)) == {"ran": False}
    assert len(alerts(outbox)) == 1


def test_abc_retry_after_jobnimbus_gave_up_is_allowed_to_try_again(abc_db, outbox, monkeypatch):
    db = abc_db
    _abc_mail(monkeypatch, outbox)

    def boom(days):
        raise RuntimeError("down")
    assert abc.run_abc_daily(db, now=ABC_NOW, mode="live", fetch=boom)["why"] == "jobnimbus"
    assert abc.run_abc_daily(db, now=ABC_NOW, mode="live", fetch=boom)["why"] == "already sent today"   # a manual rerun still waits
    assert retry.load(db, "abc_daily", "live", ABC_NOW)["due"]
    r = abc.run_abc_daily(db, now=ABC_NOW + timedelta(minutes=30), mode="live", fetch=lambda d: [_abc_delivery()],
                          fetch_job=lambda j: [], auto_retry=True)
    assert r == {"sent": True, "deliveries": 1}
    assert retry.load(db, "abc_daily", "live", ABC_NOW)["due"] is None


def test_abc_ends_with_one_final_note_to_aaron_and_greg_and_luke_send_it_by_hand(abc_db, outbox, monkeypatch):
    db = abc_db
    _abc_mail(monkeypatch, outbox, ok=_abc_is_daily)
    monkeypatch.setattr(abc, "fetch_deliveries", lambda d: [_abc_delivery()])
    monkeypatch.setattr(abc, "fetch_job_orders", lambda j: [])
    now = ABC_NOW
    abc.run_abc_daily(db, now=now, mode="live", fetch=lambda d: [_abc_delivery()])
    for _ in range(2):
        now += timedelta(minutes=30)
        retry.fire("abc_daily", now=now, mode="live", session_factory=factory(db))
    assert retry.fire("abc_daily", now=now + timedelta(minutes=30), mode="live", session_factory=factory(db)) == {"ran": False}
    aaron = alerts(outbox)
    assert len(aaron) == 2 and "twice more" in aaron[1]["text"] and "ask Claude to run it again" in aaron[1]["text"]
    ops = [m for m in outbox if set(m["to"]) == {"g@x.com", "l@x.com"}]
    assert [m["subject"] for m in ops] == ["The ABC delivery reminder is running late",
                                           "The ABC delivery reminder did not go out"]
    assert "Send ABC today's deliveries yourself" in ops[1]["text"]
    assert retry.load(db, "abc_daily", "live", ABC_NOW)["due"] is None


# --- Weather report ---

class _Weather:
    """A weather run with one build tomorrow, with the report's send result under the test's control."""

    def __init__(self, db, monkeypatch):
        from tests.test_weather_checks import TODAY
        self.reports = []
        self.alerts = []
        self.ok = False
        monkeypatch.setattr(WS, "SessionLocal", lambda: db)
        monkeypatch.setattr(db, "close", lambda: None)
        monkeypatch.setattr(WS, "_today", lambda: TODAY)
        monkeypatch.setattr("backend.activity.write", lambda *a, **k: None)
        monkeypatch.setattr(WS, "check_weather_for_job", lambda db, job_id, target, force_bamwx=False: {"status": "clear", "detail": ""})
        monkeypatch.setattr("backend.emails.config.email_mode", lambda: "live")
        monkeypatch.setattr("backend.emails.runner.run_weather_report",
                            lambda db, checked, tomorrow: self.reports.append(1) or {"jobs": 1, "failed": not self.ok})
        monkeypatch.setattr("backend.emails.runner.alert_owner",
                            lambda db, subject, lead, action, details=None, items=None, mode=None:
                            self.alerts.append((subject, lead, action)) or True)
        db.add(Job(customer_name="Cust A", address="1 Main", bucket="scheduled", jn_start_date=TODAY + timedelta(days=1),
                   latitude=39.7, longitude=-86.1, primary_trade="roofing", material_type="asphalt"))
        db.commit()


def test_weather_report_that_fails_retries_once_about_30_minutes_later(db, monkeypatch):
    w = _Weather(db, monkeypatch)
    WS.night_before_check()
    [(subject, lead, action)] = w.alerts
    assert subject == "The weather report to Greg and Luke did not send"
    assert "send the report again by itself at" in action and "30 minutes" not in action
    key = WS._retry_key("Night-before weather check")
    data = retry.load(db, key, "live", datetime.utcnow())
    assert data["due"] and data["payload"]["days"] == [1] and data["payload"]["bamwx"] is True
    due = datetime.fromisoformat(data["due"])
    w.ok = True
    out = retry.fire(key, now=due, mode="live", session_factory=factory(db))
    assert out["ran"] and len(w.reports) == 2
    assert len(w.alerts) == 1                                                   # the retry worked: no more email
    assert retry.load(db, key, "live", datetime.utcnow())["due"] is None


def test_weather_report_gets_one_retry_then_a_final_alert(db, monkeypatch):
    w = _Weather(db, monkeypatch)
    WS.night_before_check()
    key = WS._retry_key("Night-before weather check")
    due = datetime.fromisoformat(retry.load(db, key, "live", datetime.utcnow())["due"])
    retry.fire(key, now=due, mode="live", session_factory=factory(db))
    assert [a[0] for a in w.alerts] == ["The weather report to Greg and Luke did not send",
                                        "The weather report to Greg and Luke still did not send"]
    assert "even after the Scheduler tried again" in w.alerts[1][1]
    assert retry.load(db, key, "live", datetime.utcnow())["due"] is None
    assert retry.fire(key, now=due + timedelta(minutes=40), mode="live", session_factory=factory(db)) == {"ran": False}
    assert len(w.reports) == 2                                                  # one try, one retry, no more


# --- The timer itself ---

def test_a_failure_sets_a_one_off_timer_30_minutes_out(db, jn, outbox, monkeypatch):
    fake = FakeScheduler()
    retry.set_scheduler(fake)
    _three_queued(db, jn)
    _flaky_send(monkeypatch, outbox, bad_to=["bob@example.com"])
    R.run_weekly(db, THU, mode="live")
    fn, trigger, kw = fake.jobs["email_retry_weekly"]
    assert trigger == "date" and kw["run_date"].replace(tzinfo=None) == LATER and fn is retry.fire
    _flaky_send(monkeypatch, outbox)
    R.run_weekly(db, THU + timedelta(minutes=5), mode="live")                   # fixed by hand: the timer is removed
    assert "email_retry_weekly" not in fake.jobs


def test_clock_words_use_indianapolis_time():
    assert retry.clock_words(datetime(2026, 10, 8, 14, 35)) == "10:35 AM"      # October: Eastern daylight time
    assert retry.clock_words(datetime(2026, 11, 12, 22, 0)) == "5:00 PM"       # November: Eastern standard time
    assert retry.clock_words(datetime(2026, 11, 13, 5, 5)) == "12:05 AM"
