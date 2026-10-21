"""Push to JobNimbus: Greg's booking steps, done once each, in his order."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.job import Job
from backend.models.pm import PM, Crew
from backend.services import jn_booking as B

TZ = ZoneInfo("America/Indiana/Indianapolis")
BUILD = date(2030, 10, 29)  # a Tuesday, safely in the future
JOB = "jobjn1"


class FakeJN:
    def __init__(self, wo_status="New", fail_on=None, wo_start=0, job_status="Schedule Job", extra_wos=()):
        self.calls = []
        self.fail_on = fail_on
        self.job_status = job_status
        self.extra_wos = list(extra_wos)
        self.wo = {"jnid": "wo1", "number": "WO-11853", "recid": 11853, "record_type_name": "Roofing",
                   "status_name": wo_status, "is_active": True, "date_start": wo_start,
                   "subcontractors": [], "owners": [{"id": "rep1"}]}
        self.notes = []

    def get(self, endpoint, params=None):
        self.calls.append(("GET", endpoint))
        if endpoint == "account/settings":
            return {"workflows": [
                {"object_type": "workorder", "name": "Roofing", "status": [{"id": 471, "name": "Schedule"},
                                                                          {"id": 472, "name": "Pending Start"}]},
                {"object_type": "workorder", "name": "Gutters", "status": [{"id": 481, "name": "Pending Start"}]},
                {"object_type": "job", "name": "Retail", "status": [{"id": 446, "name": "Schedule Job"},
                                                                    {"id": 447, "name": "Pending Start Date"}]},
            ], "taskTypes": [{"TaskTypeId": 23, "TypeName": "Build Block"}]}
        if endpoint == "account/users":
            return [{"id": "luke_user", "first_name": "Luke", "last_name": "Mroz", "is_active": True},
                    {"id": "rep1", "first_name": "Pat", "last_name": "Rep", "is_active": True}]
        if endpoint == "contacts":
            return {"results": [
                {"jnid": "dct", "display_name": "DCT Construction - Roof Crew"},
                {"jnid": "dct_co", "display_name": "DCT Construction - Company"},
                {"jnid": "luke_sub", "display_name": "Luke Mroz - Indy Roof and Restoration"},
            ]}
        if endpoint == f"jobs/{JOB}":
            return {"jnid": JOB, "record_type_name": "Retail", "status_name": self.job_status, "sales_rep": "rep1", "sales_rep_name": "Pat Rep",
                    "subcontractors": [], "description": ""}
        if endpoint == "v2/workorders":
            return {"results": [self.wo, {"jnid": "wo2", "number": "WO-11854", "recid": 11854,
                                          "record_type_name": "Gutters", "status_name": "New", "is_active": True},
                                *self.extra_wos]}
        if endpoint == "activities":
            return {"activity": self.notes}
        if endpoint == "tasks":
            return {"results": [
                {"jnid": "t1", "title": "Send Work Order & Add Job Date to Job File", "is_completed": False},
                {"jnid": "t2", "title": "order materials & begin trade prep", "is_completed": False},
                {"jnid": "t3", "title": "Order Materials & begin trade prep", "is_completed": True},
                {"jnid": "t4", "title": "review aging work order", "is_completed": False},
            ]}
        raise AssertionError(endpoint)

    def _write(self, method, endpoint, body):
        self.calls.append((method, endpoint, body))
        if self.fail_on and self.fail_on(method, endpoint, body):
            raise RuntimeError("JobNimbus said no")
        return {}

    def put(self, endpoint, body):
        return self._write("PUT", endpoint, body)

    def post(self, endpoint, body):
        return self._write("POST", endpoint, body)

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def live(monkeypatch):
    monkeypatch.setenv("JN_BOOKING_MODE", "live")


def planned_job(db, **kw):
    pm = PM(name="Luke Mroz")
    crew = Crew(name="DCT Construction", trades=["roofing"])
    db.add_all([pm, crew])
    db.flush()
    job = Job(customer_name="Test Customer", address="1 Main St", jn_job_id=JOB, bucket="to_schedule",
              primary_trade="roofing", planned_date=BUILD, planned_pm_id=pm.id, planned_crew_id=crew.id,
              ready_status="clear", ready_input="", ready_input_hash=None, duration_days=1)
    for k, v in kw.items():
        setattr(job, k, v)
    db.add(job)
    db.commit()
    return job


def test_books_the_job_with_gregs_steps_in_order(db):
    job = planned_job(db)
    jn = FakeJN()
    result = B.push(db, "Greg Russell", jn=jn)
    assert result["booked"] == 1, result
    w = jn.writes()
    midnight = int(datetime(2030, 10, 29, tzinfo=TZ).timestamp())

    # 1. date, crew and Luke on the roofing work order (not the gutters one), before the status
    assert w[0][:2] == ("PUT", "v2/workorders/wo1")
    assert w[0][2]["jnid"] == "wo1"  # JobNimbus refuses a v2 update without it
    assert w[0][2]["date_start"] == midnight and w[0][2]["all_day"] is True
    assert w[0][2]["all_day_start_date"] == "2030-10-29" == w[0][2]["all_day_end_date"]
    assert [s["id"] for s in w[0][2]["subcontractors"]] == ["dct", "luke_sub"]
    assert [o["id"] for o in w[0][2]["owners"]] == ["rep1", "luke_user"]
    assert "status" not in w[0][2]
    # 2. then Pending Start, on its own, with the Roofing workflow's id
    assert w[1] == ("PUT", "v2/workorders/wo1", {"jnid": "wo1", "status": 472})
    # 3. job to Pending Start Date with the same date
    assert w[2][:2] == ("PUT", f"jobs/{JOB}")
    assert w[2][2]["status"] == 447 and w[2][2]["date_start"] == midnight and "date_end" not in w[2][2]
    assert w[2][2]["all_day"] is True and w[2][2]["all_day_start_date"] == "2030-10-29" == w[2][2]["all_day_end_date"]
    # 4. rep note
    assert w[3][:2] == ("POST", "activities")
    assert w[3][2]["note"] == "@PatRep roof scheduled Tuesday 10/29"
    # 5. Build Block for the rep, 4:00 to 4:59pm build day
    assert w[4][:2] == ("POST", "tasks")
    bb = w[4][2]
    assert bb["record_type"] == 23 and bb["title"] == "Build Block" and bb["owners"] == [{"id": "rep1"}]
    assert datetime.fromtimestamp(bb["date_start"], TZ).strftime("%H:%M") == "16:00"
    assert datetime.fromtimestamp(bb["date_end"], TZ).strftime("%H:%M") == "16:59"
    # 6. only the two open tasks Greg closes
    assert w[5:] == [("PUT", "tasks/t1", {"is_completed": True}), ("PUT", "tasks/t2", {"is_completed": True})]

    db.refresh(job)
    assert B.already_sent(job) and job.jn_push_error is None
    # The app never books it itself: the sync does, so the build queue emails react as usual
    assert job.bucket == "to_schedule" and job.planned_date == BUILD


def test_a_second_push_sends_nothing(db):
    planned_job(db)
    B.push(db, "Greg", jn=FakeJN())
    jn = FakeJN()
    result = B.push(db, "Greg", jn=jn)
    assert result["results"][0]["status"] == "skipped" and jn.writes() == []


MIDNIGHT = int(datetime(2030, 10, 29, tzinfo=TZ).timestamp())


def test_a_push_that_stops_halfway_never_repeats_the_status_change(db):
    job = planned_job(db)
    jn = FakeJN(fail_on=lambda m, e, b: e == f"jobs/{JOB}")
    result = B.push(db, "Greg", jn=jn)
    assert result["failed"] == 1
    db.refresh(job)
    assert "JobNimbus didn't accept" in job.jn_push_error
    assert job.jn_push_steps["work_order_status"] is True and not job.jn_push_steps.get("job_status")

    jn2 = FakeJN(wo_status="Pending Start", wo_start=MIDNIGHT)  # JobNimbus now shows it Pending Start
    assert B.push(db, "Greg", jn=jn2)["booked"] == 1
    endpoints = [c[1] for c in jn2.writes()]
    assert "v2/workorders/wo1" not in endpoints  # neither the date nor the status sent again
    assert endpoints[0] == f"jobs/{JOB}"


def test_moving_the_plan_to_a_new_day_starts_a_fresh_booking(db):
    job = planned_job(db)
    B.push(db, "Greg", jn=FakeJN())
    job.planned_date = date(2030, 10, 30)
    db.commit()
    jn = FakeJN()
    assert B.push(db, "Greg", jn=jn)["booked"] == 1
    assert jn.writes()[0][2]["all_day_start_date"] == "2030-10-30"


def test_refuses_a_work_order_already_pending_start(db):
    job = planned_job(db)
    jn = FakeJN(wo_status="Pending Start")
    result = B.push(db, "Greg", jn=jn)
    assert result["results"][0]["status"] == "failed"
    assert "booked it by hand" in result["results"][0]["reason"] and jn.writes() == []


def test_new_notes_are_checked_before_anything_is_sent(db):
    job = planned_job(db)
    jn = FakeJN()
    jn.notes = [{"record_type_name": "Note", "note": "Customer wants to wait until spring",
                 "date_created": 1, "created_by_name": "Joe"}]

    class AI:
        class messages:
            @staticmethod
            def create(**kw):
                text = json.dumps({"blockers": [{"issue": "Customer asked to wait", "quote": "wait", "source": "Note"}]})
                return type("R", (), {"content": [type("B", (), {"type": "text", "text": text})()]})()

    result = B.push(db, "Greg", jn=jn, ai_client=AI())
    assert result["results"][0]["status"] == "failed"
    assert "Answer the ready check" in result["results"][0]["reason"]
    assert jn.writes() == []
    db.refresh(job)
    assert job.ready_status == "flagged"


@pytest.mark.parametrize("change, reason", [
    ({"ready_status": "hold"}, "On hold"),
    ({"ready_status": "flagged"}, "Needs a decision"),
    ({"planned_crew_id": None}, "Pick a crew"),
    ({"jn_job_id": None}, "Not a JobNimbus job"),
])
def test_jobs_that_arent_ready_are_skipped(db, change, reason):
    planned_job(db, **change)
    jn = FakeJN()
    result = B.push(db, "Greg", jn=jn)
    assert result["results"][0]["status"] == "skipped" and reason in result["results"][0]["reason"]
    assert jn.writes() == []


def test_off_by_default_and_test_mode_sends_only_the_test_job(db, monkeypatch):
    job = planned_job(db)
    monkeypatch.delenv("JN_BOOKING_MODE")
    assert "turned off" in B.preview(db)["items"][0]["reason"]
    monkeypatch.setenv("JN_BOOKING_MODE", "test")
    monkeypatch.setenv("JN_BOOKING_TEST_JOBS", "someotherjob")
    assert "Test mode" in B.preview(db)["items"][0]["reason"]
    assert FakeJN().writes() == [] and B.push(db, "Greg", jn=FakeJN())["booked"] == 0
    monkeypatch.setenv("JN_BOOKING_TEST_JOBS", f"someotherjob, {JOB}")
    assert B.preview(db)["ready_count"] == 1


def test_crew_matches_its_jobnimbus_name():
    lk = B.Lookups(FakeJN())
    assert B.crew_jn_name(Crew(name="DCT Construction"), lk) == "DCT Construction - Roof Crew"
    assert B.crew_jn_name(Crew(name="dct construction - roof crew"), lk) == "DCT Construction - Roof Crew"
    assert B.crew_jn_name(Crew(name="Nobody"), lk) is None
    assert B.crew_jn_name(Crew(name="X", jn_name="DCT Construction - Company"), lk) == "DCT Construction - Company"


def test_unknown_crew_says_where_to_fix_it(db):
    job = planned_job(db)
    db.get(Crew, job.planned_crew_id).name = "Nobody"
    db.commit()
    result = B.push(db, "Greg", jn=FakeJN())
    assert "Settings > Crews" in result["results"][0]["reason"]


def test_rep_note_reads_like_gregs():
    assert B.rep_note_text("Pat Rep", "roofing", date(2026, 10, 27)) == "@PatRep roof scheduled Tuesday 10/27"
    assert B.rep_note_text(None, "gutters", date(2026, 11, 2)) == "gutters scheduled Monday 11/2"


def test_a_status_change_that_reached_jobnimbus_but_timed_out_is_not_sent_again(db):
    job = planned_job(db)
    jn = FakeJN(fail_on=lambda m, e, b: b.get("status") == 472)  # timed out, but JobNimbus applied it
    B.push(db, "Greg", jn=jn)
    db.refresh(job)
    assert job.jn_push_steps.get("work_order") and not job.jn_push_steps.get("work_order_status")

    jn2 = FakeJN(wo_status="Pending Start", wo_start=MIDNIGHT)
    assert B.push(db, "Greg", jn=jn2)["booked"] == 1
    assert all(c[1] != "v2/workorders/wo1" for c in jn2.writes())


def test_refuses_when_another_work_order_or_the_job_is_already_booked(db):
    planned_job(db)
    other = {"jnid": "wo3", "number": "WO-3", "record_type_name": "Siding", "status_name": "Pending Start",
             "is_active": True}
    jn = FakeJN(extra_wos=[other])
    assert "booked it by hand" in B.push(db, "Greg", jn=jn)["results"][0]["reason"] and jn.writes() == []
    jn = FakeJN(job_status="Pending Start Date")
    assert "already Pending Start Date" in B.push(db, "Greg", jn=jn)["results"][0]["reason"] and jn.writes() == []


def test_skips_closed_work_orders_and_refuses_two_open_ones(db):
    planned_job(db)
    old = {"jnid": "old", "number": "WO-1", "recid": 1, "record_type_name": "Roofing", "status_name": "Completed",
           "is_active": True}
    jn = FakeJN(extra_wos=[old])
    assert B.push(db, "Greg", jn=jn)["booked"] == 1
    assert jn.writes()[0][1] == "v2/workorders/wo1"

    job2 = planned_job(db, jn_job_id=JOB + "x")
    two = {"jnid": "wo9", "number": "WO-9", "record_type_name": "Roofing", "status_name": "New", "is_active": True}
    with pytest.raises(B.BookingError, match="more than one open Roofing"):
        B.pick_work_order(job2, [FakeJN().wo, two])


def test_a_half_finished_push_survives_the_sync_and_finishes(db):
    from backend.services import jobnimbus as jnapi
    job = planned_job(db)
    B.push(db, "Greg", jn=FakeJN(fail_on=lambda m, e, b: e == "activities"))
    job.bucket = "scheduled"  # the sync saw Pending Start Date
    jnapi._apply_calendar(job, {}, None, None, "")
    db.commit()
    assert job.planned_date == BUILD  # plan kept so the button can finish
    jn = FakeJN(wo_status="Pending Start", wo_start=MIDNIGHT, job_status="Pending Start Date")
    result = B.push(db, "Greg", jn=jn)
    assert result["booked"] == 1
    assert [c[1] for c in jn.writes()][0] == "activities"
    jnapi._apply_calendar(job, {}, None, None, "")
    assert job.planned_date is None and job.jn_push_steps is None  # done: plan and log cleared together


def test_stops_the_whole_push_when_jobnimbus_errors(db):
    planned_job(db)
    planned_job(db, jn_job_id=JOB + "2")  # never reached
    jn = FakeJN(fail_on=lambda m, e, b: True)
    result = B.push(db, "Greg", jn=jn)
    assert len(result["results"]) == 1 and result["results"][0]["jn_error"]


def test_only_office_ops_and_owners_can_book(db, monkeypatch):
    from backend.models.email import TeamContact
    from backend.routers.schedule import can_book
    from backend.services.auth import ClerkUser
    db.add_all([TeamContact(jn_name="Pat Rep", display_name="Pat", role="rep", email="pat@x.com"),
                TeamContact(jn_name="Nikka", display_name="Nikka", role="office", email="nikka@x.com")])
    db.commit()
    user = lambda email: ClerkUser({"sub": "u", "email": email, "approved": True})  # noqa: E731
    assert not can_book(db, user("pat@x.com"))
    assert can_book(db, user("NIKKA@x.com"))
    assert not can_book(db, user("stranger@x.com"))


def test_an_old_job_end_date_before_the_new_start_is_cleared(db):
    planned_job(db)
    jn = FakeJN()
    orig = jn.get
    jn.get = lambda e, p=None: {**orig(e, p), "date_end": 1} if e == f"jobs/{JOB}" else orig(e, p)
    B.push(db, "Greg", jn=jn)
    job_put = next(c for c in jn.writes() if c[1] == f"jobs/{JOB}")
    assert job_put[2]["date_end"] == 0


# --- taking a booked job off the calendar, and moving it ---

def booked_jn(**kw):
    jn = FakeJN(wo_status="Pending Start", wo_start=MIDNIGHT, job_status="Pending Start Date", **kw)
    orig = jn.get

    def get(e, p=None):
        if e == "tasks":
            return {"results": [{"jnid": "bb", "record_type_name": "Build Block", "is_completed": False,
                                 "date_start": B.local_ts(BUILD, 16)},
                                {"jnid": "bb_other", "record_type_name": "Build Block", "is_completed": False,
                                 "date_start": B.local_ts(date(2030, 11, 5), 16)}]}
        return orig(e, p)
    jn.get = get
    return jn


def test_unbook_reverses_the_booking_in_jobnimbus(db):
    job = planned_job(db, bucket="scheduled", jn_status="Pending Start Date", jn_start_date=BUILD)
    jn = booked_jn()
    out = B.unbook(db, job, "Greg", "Weather Pre-Build", jn=jn)
    assert out["status"] == "unbooked" and out["build_blocks_closed"] == 1
    w = jn.writes()
    # The reason goes on in the same change as the status, so JobNimbus's taken-off messages read it
    assert w[0] == ("PUT", "v2/workorders/wo1", {"jnid": "wo1", "date_start": 0, "all_day": False,
                                                 "all_day_start_date": "", "all_day_end_date": "",
                                                 "Reschedule Reason": "Weather", "status": 471})
    assert w[1] == ("PUT", f"jobs/{JOB}", {"date_start": 0, "all_day": False, "all_day_start_date": "",
                                           "all_day_end_date": "", "status": 446})
    assert w[2][2]["note"] == "@PatRep roof moved off Tuesday 10/29 (Weather Pre-Build)"
    assert w[3] == ("PUT", "tasks/bb", {"is_completed": True})  # only that day's Build Block
    assert len(w) == 4 and job.jn_push_steps is None
    assert out["customer_told"] is True


def test_unbook_twice_changes_nothing_more(db):
    job = planned_job(db, bucket="scheduled", jn_status="Pending Start Date", jn_start_date=None)
    jn = FakeJN(wo_status="Schedule", job_status="Schedule Job")
    out = B.unbook(db, job, "Greg", "Weather", jn=jn)
    assert out["status"] == "unbooked" and jn.writes() == []


def test_unbook_respects_the_switch(db, monkeypatch):
    job = planned_job(db)
    monkeypatch.setenv("JN_BOOKING_MODE", "off")
    jn = booked_jn()
    assert B.unbook(db, job, "Greg", "Weather", jn=jn)["status"] == "skipped" and jn.writes() == []


def test_move_changes_only_the_dates_so_the_build_day_messages_dont_go_again(db):
    job = planned_job(db, bucket="scheduled", jn_status="Pending Start Date", jn_start_date=BUILD,
                      jn_crews=["DCT Construction - Roof Crew"], jn_pm="Luke Mroz")
    job.planned_crew_id = job.planned_pm_id = None
    db.commit()
    jn = booked_jn()
    new_day = date(2030, 11, 5)
    out = B.move(db, job, new_day, "Greg", "Customer asked", jn=jn)
    assert out["status"] == "booked" and out["moved_in_place"], out
    w = jn.writes()
    # The work order never leaves Pending Start: no status in any change, so no Build Day email or 1-hour text
    assert not any("status" in c[2] for c in w if c[1].startswith(("v2/workorders", "jobs/")))
    assert w[0] == ("PUT", "v2/workorders/wo1", {
        "jnid": "wo1", "date_start": B.local_midnight(new_day), "all_day": True,
        "all_day_start_date": "2030-11-05", "all_day_end_date": "2030-11-05",
        "Reschedule Reason": "Customer request"})   # the date change + reason sends the "moved" messages
    assert w[1][1] == f"jobs/{JOB}" and w[1][2]["all_day_start_date"] == "2030-11-05"
    assert w[2][2]["note"] == "@PatRep roof moved off Tuesday 10/29 (Customer asked), moving to Tuesday 11/5"
    assert ("PUT", "tasks/bb", {"is_completed": True}) in w          # old day's Build Block done
    bb = next(c for c in w if c[1] == "tasks" and c[0] == "POST")[2]
    assert bb["date_start"] == B.local_ts(new_day, 16) and bb["owners"] == [{"id": "rep1"}]
    assert job.jn_start_date == new_day and job.jn_push_steps["date"] == "2030-11-05"
    # A second click on the same day does nothing
    n = len(jn.writes())
    assert B.move(db, job, new_day, "Greg", "Customer asked", jn=jn)["reason"] == "Already booked on that day."
    assert len(jn.writes()) == n


def test_move_tells_the_customer_once_when_two_work_orders_are_booked(db):
    job = planned_job(db, bucket="scheduled", jn_status="Pending Start Date", jn_start_date=BUILD)
    gutters = {"jnid": "wo3", "number": "WO-11855", "record_type_name": "Gutters", "status_name": "Pending Start",
               "is_active": True, "date_start": MIDNIGHT}
    jn = booked_jn(extra_wos=[gutters])
    assert B.move(db, job, date(2030, 11, 5), "Greg", "Weather", jn=jn)["status"] == "booked"
    wo_puts = [c for c in jn.writes() if c[1].startswith("v2/workorders/")]
    assert [(c[1], c[2]["Reschedule Reason"]) for c in wo_puts] == [
        ("v2/workorders/wo3", ""), ("v2/workorders/wo1", "Weather")]   # main one last, the only one with a reason


def test_move_books_fresh_when_jobnimbus_has_nothing_booked(db):
    job = planned_job(db, bucket="scheduled", jn_status="Schedule Job", jn_start_date=None)
    jn = FakeJN(wo_status="Schedule")
    out = B.move(db, job, date(2030, 11, 5), "Greg", "Weather", jn=jn)
    assert out["status"] == "booked" and not out.get("moved_in_place")
    assert ("PUT", "v2/workorders/wo1", {"jnid": "wo1", "status": 472}) in jn.writes()


def test_move_refuses_a_day_in_the_past(db):
    job = planned_job(db)
    assert B.move(db, job, date(2020, 1, 1), "Greg", "", jn=FakeJN())["status"] == "failed"


def test_a_second_move_to_the_same_day_does_nothing(db):
    job = planned_job(db)
    job.jn_push_steps = {"date": "2030-11-05", **{s: True for s in B.STEPS}}
    db.commit()
    jn = FakeJN()
    assert B.move(db, job, date(2030, 11, 5), "Greg", "Weather", jn=jn)["reason"] == "Already booked on that day."
    assert jn.writes() == []


def test_move_waits_for_another_push_or_move(db):
    job = planned_job(db)
    B._push_lock.acquire()
    try:
        out = B.move(db, job, date(2030, 11, 5), "Greg", "Weather", jn=FakeJN())
    finally:
        B._push_lock.release()
    assert out["status"] == "failed" and "Already moving" in out["reason"]


@pytest.mark.parametrize("reason,category", [
    ("Weather", "Weather"), ("Weather Pre-Build: storms Thursday", "Weather"), ("Customer asked", "Customer request"),
    ("Customer Related", "Customer request"), ("Crew", "Other"), ("Materials", "Other"),
    ("Crew Unavailable", "Other"), ("Scope Change", "Other"), ("", "Other"),
])
def test_only_weather_and_customer_requests_are_named_to_the_customer(reason, category):
    assert B.reschedule_category(reason) == category


def test_a_normal_push_clears_the_reschedule_reason(db):
    job = planned_job(db)
    jn = FakeJN()
    assert B.book_job(db, job, "Greg", jn=jn)["status"] == "booked"
    wo_date = next(c for c in jn.writes() if c[1] == "v2/workorders/wo1" and c[2].get("all_day"))
    assert wo_date[2]["Reschedule Reason"] == ""   # so the usual Build Day email goes


def test_a_plan_is_cleared_when_jobnimbus_has_the_work_order_booked_but_the_job_status_lags(db):
    # Greg books the work order by hand (or the job's status hasn't caught up): the job is still
    # To Schedule, but JobNimbus has it booked. The old plan must not sit in the Push count.
    from backend.services import jobnimbus as jnapi
    job = planned_job(db)
    wo = {"number": "WO-11853", "trade": "Roofing", "status": "Pending Start", "start": "2030-11-17",
          "crews": [], "pm": None, "internal_note": "", "customer_note": "", "labor": []}
    jnapi._apply_calendar(job, {}, [wo], None, "")
    assert job.bucket == "to_schedule" and job.planned_date is None
    assert job.jn_start_date == date(2030, 11, 17)


def test_a_plan_stays_while_the_work_order_is_not_booked(db):
    from backend.services import jobnimbus as jnapi
    job = planned_job(db)
    wo = {"number": "WO-11853", "trade": "Roofing", "status": "Schedule", "start": None,
          "crews": [], "pm": None, "internal_note": "", "customer_note": "", "labor": []}
    jnapi._apply_calendar(job, {}, [wo], None, "")
    assert job.planned_date == BUILD


def test_not_built_clears_the_plan_for_the_day_it_missed(db):
    from types import SimpleNamespace
    from backend.routers.jobs import mark_not_built
    from backend.schemas.job import NotBuiltRequest
    job = planned_job(db, jn_status="Schedule Job", rescheduled_count=0, priority_bump=0.0)
    mark_not_built(job.id, NotBuiltRequest(reason="Weather Pre-Build"), db=db,
                   user=SimpleNamespace(email=None, name="Greg"))
    db.refresh(job)
    assert job.bucket == "to_schedule" and job.planned_date is None and job.planned_crew_id is None
    assert B.candidates(db) == []   # not left in the Push to JobNimbus count
