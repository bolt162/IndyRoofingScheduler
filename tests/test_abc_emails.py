"""ABC Supply emails: the daily delivery reminder and the Not Built postponement. Nothing leaves the machine."""
import pathlib
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.emails import abc
from backend.models.email import EmailLog, TeamContact
from backend.models.job import Job


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    s.add_all([TeamContact(jn_name="Luke Mroz", display_name="Luke Mroz", role="pm", email="l@x.com", phone="3170000001"),
               TeamContact(jn_name="Greg Russell", display_name="Greg Russell", role="ops", email="g@x.com", phone="3170000002")])
    s.commit()
    yield s
    s.close()


@pytest.fixture
def outbox(monkeypatch):
    class Box(list):
        now = None
    sent = Box()

    def fake_send(db, job_id, email, to, customer_name="", mode=None):
        sent.append({"template": email.template, "to": to, "subject": email.subject, "text": email.text, "mode": mode})
        db.add(EmailLog(job_id=job_id, template=email.template, recipient=",".join(to), subject=email.subject,
                        mode=mode, result="sent", created_at=sent.now))
        db.commit()
        return True
    monkeypatch.setattr(abc, "send", fake_send)
    return sent


def delivery(job="J-1", day=date(2026, 11, 10), jn_job_id="a"):
    return {"jn_job_id": jn_job_id, "job_number": job, "customer": "Pat Smith", "address": "1 Main St, Zionsville",
            "abc_order": "C12-1", "day": day}


def noon_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 17, 0)   # noon Indianapolis (EST or EDT is close enough: same day)


def at(outbox, d: date) -> datetime:
    outbox.now = noon_utc(d)
    return outbox.now


def test_days_covered():
    assert abc.delivery_days(date(2026, 11, 9)) == [date(2026, 11, 10)]                     # Monday -> Tuesday
    assert abc.delivery_days(date(2026, 11, 6)) == [date(2026, 11, 7), date(2026, 11, 9)]   # Friday -> Sat + Mon
    assert abc.delivery_days(date(2026, 11, 7)) == []                                       # weekend
    assert abc.delivery_days(date(2026, 11, 26)) == [date(2026, 11, 27)]                    # holidays don't matter


def test_parse_order_skips_drafts_and_reads_abc_number():
    base = {"supplier": {"type": "ABC Supply", "logs": [{"id": "C12-9"}]}, "status_name": "Order Received",
            "related": [{"type": "job", "id": "j", "number": "J-26802", "name": "‪Susan Priest - J-26802"}],
            "address": {"address_line1": "3 Rd", "city": "Roachdale"}, "date_materialorder": 1794243600}
    p = abc.parse_order(base)
    assert (p["job_number"], p["customer"], p["abc_order"], p["day"]) == ("J-26802", "Susan Priest", "C12-9", date(2026, 11, 9))
    dup = {**base, "related": [{"type": "job", "id": "j", "number": "J-25770", "name": "David Boyd - J-25770 (1)"}]}
    assert abc.parse_order(dup)["customer"] == "David Boyd"
    done = {**base, "supplier": {"type": "ABC Supply", "logs": [{"id": "C12-27593888", "msg": "orderReceived"}, {"id": "2016101156", "msg": "fulfilled"}]}}
    assert abc.parse_order(done)["abc_order"] == "C12-27593888"   # not the invoice number added when fulfilled
    assert abc.parse_order({**base, "status_name": "Draft"}) is None
    assert abc.parse_order({**base, "supplier": {"type": "Beacon"}}) is None


def test_daily_sends_once_and_lists_deliveries(db, outbox):
    now = at(outbox, date(2026, 11, 9))
    r = abc.run_abc_daily(db, now=now, mode="test", fetch=lambda days: [delivery()])
    assert r == {"sent": True, "deliveries": 1}
    body = outbox[0]["text"]
    assert "J-1" in body and "C12-1" in body and "(317) 000-0001" in body and "(317) 000-0002" in body
    assert "Lead PM" in body and "Tuesday, Nov 10" in outbox[0]["subject"]
    assert abc.run_abc_daily(db, now=now, mode="test", fetch=lambda days: [delivery()])["why"] == "already sent today"
    assert len(outbox) == 1


def test_daily_friday_splits_days_and_empty_day_still_sends(db, outbox):
    fri = at(outbox, date(2026, 11, 6))
    abc.run_abc_daily(db, now=fri, mode="test", fetch=lambda days: [delivery(day=date(2026, 11, 7)), delivery("J-2", date(2026, 11, 9))])
    assert "Saturday, Nov 7" in outbox[0]["text"] and "Monday, Nov 9" in outbox[0]["text"]
    assert abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 9)), mode="test", fetch=lambda days: [])["why"] == "no deliveries"
    assert len(outbox) == 1


def test_daily_skips_weekend_and_jobs_back_in_the_queue(db, outbox):
    assert abc.run_abc_daily(db, now=noon_utc(date(2026, 11, 7)), mode="test", fetch=lambda d: [])["sent"] is False
    db.add(Job(jn_job_id="a", jn_number="J-1", customer_name="Pat Smith", address="x", bucket="to_schedule", primary_trade="roofing"))
    db.commit()
    abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 9)), mode="test", fetch=lambda days: [delivery()])
    assert not outbox


def test_daily_missing_phone_or_failed_jobnimbus_sends_nothing_and_doesnt_retry(db, outbox):
    def boom(days):
        raise RuntimeError("down")
    now = at(outbox, date(2026, 11, 9))
    assert abc.run_abc_daily(db, now=now, mode="test", fetch=boom)["why"] == "jobnimbus"
    assert all(m["template"] != abc.DAILY for m in outbox)           # only the note to Greg and Luke went
    assert abc.run_abc_daily(db, now=now, mode="test", fetch=boom)["why"] == "already sent today"
    db.query(TeamContact).filter(TeamContact.role == "ops").update({"phone": None})
    db.commit()
    assert abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 10)), mode="test", fetch=boom)["why"] == "missing phone"


def test_postponed(db, outbox):
    job = Job(id=5, jn_job_id="a", jn_number="J-1", customer_name="Pat Smith", address="x", bucket="to_schedule", primary_trade="roofing")
    assert abc.send_postponed(db, job, "Weather Mid-Build", mode="test", fetch=lambda j: delivery())["why"] == "mid-build"
    assert abc.send_postponed(db, job, "Crew Unavailable", mode="test", fetch=lambda j: delivery(), trade="gutters")["why"] == "gutters"
    assert abc.send_postponed(db, job, "Crew Unavailable", mode="test", fetch=lambda j: None)["why"] == "no order"
    assert not outbox
    assert abc.send_postponed(db, job, "Crew Unavailable", mode="test", fetch=lambda j: delivery())["sent"] is True
    assert "C12-1" in outbox[0]["text"] and "postponed" in outbox[0]["text"]


def test_gregs_number_is_never_in_the_code():
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in list((root / "backend").rglob("*.py")) + list((root / "frontend-react" / "src").rglob("*.ts*")):
        assert "945-7694" not in f.read_text(errors="ignore"), f


def test_not_built_note_mentions_rep_and_pm(db, monkeypatch):
    from backend.services import jn_booking as B
    job = Job(id=7, jn_job_id="a", jn_number="J-1", customer_name="Pat", address="x", bucket="to_schedule",
              primary_trade="roofing", sales_rep="Pat Rep", jn_pm="Luke Mroz")
    assert B.moved_note_text(job, {"sales_rep_name": "Pat Rep"}, None, "Weather", mention_pm=True).startswith("@PatRep @LukeMroz ")
    assert "@LukeMroz" not in B.moved_note_text(job, {"sales_rep_name": "Pat Rep"}, None, "Weather")
    notes = []
    monkeypatch.setattr(B, "allowed", lambda j: True)
    import backend.services.jobnimbus as svc
    monkeypatch.setattr(svc, "push_note_to_jn", lambda jid, text: notes.append(text))
    B.not_built_note(db, job, "Crew Unavailable", "sick", "Greg Russell")
    assert notes[0].startswith("[NOT BUILT] @PatRep @LukeMroz Build rescheduled. Reason: Crew Unavailable. Detail: sick. Marked by Greg Russell on ")


def booked_job(jn_job_id, number, name, start, trade="Roofing", status="Pending Start", bucket="scheduled"):
    return Job(jn_job_id=jn_job_id, jn_number=number, customer_name=name, address="x", bucket=bucket, primary_trade="roofing",
               jn_work_orders=[{"number": "1", "trade": trade, "status": status, "start": start}])


def order(jn_job_id, number, day, abc="C12-9", open_=True):
    return {"jn_job_id": jn_job_id, "job_number": number, "customer": "Pat Smith", "address": "1 Main St", "abc_order": abc,
            "day": day, "open": open_}


def test_rescheduled_build_follows_the_labor_order(db, outbox):
    """Andrew Bolton, 11/6: material order said Mon Nov 2 (rained out), labor order moved to Mon Nov 9."""
    db.add(booked_job("bolton", "J-26114", "Andrew Bolton", "2026-11-09"))
    db.commit()
    jobs = {"bolton": [order("bolton", "J-26114", date(2026, 11, 2), "C12-27633323")]}
    r = abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 6)), mode="test", fetch=lambda days: [],
                          fetch_job=lambda j: jobs.get(j, []))
    assert r == {"sent": True, "deliveries": 1}
    text = outbox[0]["text"]
    assert "J-26114" in text and "C12-27633323" in text and "Rescheduled from Monday, Nov 2" in text


def test_order_on_the_day_is_dropped_when_the_build_moved_away(db, outbox):
    db.add(booked_job("moved", "J-2", "Moved Away", "2026-11-12"))
    db.add(Job(jn_job_id="held", jn_number="J-3", customer_name="Held", address="x", bucket="to_schedule", primary_trade="roofing"))
    db.commit()
    r = abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 9)), mode="test",
                          fetch=lambda days: [order("moved", "J-2", date(2026, 11, 10)), order("held", "J-3", date(2026, 11, 10))],
                          fetch_job=lambda j: [])
    assert r["why"] == "no deliveries" and not outbox


def test_picks_the_order_for_that_day_and_skips_gutters_and_unordered_builds(db, outbox):
    """Chris Watkins has an old open order (Oct 16) and the real one (Nov 10): the one dated the build day wins."""
    db.add_all([booked_job("watkins", "J-23781", "Chris Watkins", "2026-11-10"),
                booked_job("gutter", "J-5", "Gutter Only", "2026-11-10", trade="Gutters"),
                booked_job("beacon", "J-6", "Other Supplier", "2026-11-10")])
    db.commit()
    jobs = {"watkins": [order("watkins", "J-23781", date(2026, 11, 10), "C12-NEW"), order("watkins", "J-23781", date(2026, 10, 16), "C12-OLD"),
                        order("watkins", "J-23781", date(2026, 9, 1), "C12-DONE", open_=False)],
            "gutter": [order("gutter", "J-5", date(2026, 11, 10))]}
    # the same order also comes back by date: listed once
    abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 9)), mode="test",
                      fetch=lambda days: [order("watkins", "J-23781", date(2026, 11, 10), "C12-NEW")], fetch_job=lambda j: jobs.get(j, []))
    text = outbox[0]["text"]
    assert text.count("J-23781") == 1 and "C12-NEW" in text and "C12-OLD" not in text and "Rescheduled" not in text
    assert "J-5" not in text and "J-6" not in text


def test_follow_up_siding_build_counts(db, outbox):
    db.add(booked_job("boyd", "J-25770", "David Boyd", "2026-11-10", trade="Siding", bucket="other_trades"))
    db.commit()
    abc.run_abc_daily(db, now=at(outbox, date(2026, 11, 9)), mode="test", fetch=lambda days: [],
                      fetch_job=lambda j: [order("boyd", "J-25770", date(2026, 11, 10))])
    assert "J-25770" in outbox[0]["text"]
