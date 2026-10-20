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
