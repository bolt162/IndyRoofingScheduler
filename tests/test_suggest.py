"""Suggest builds: fills the week around what's already there, never touches plans or JobNimbus."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.job import Job
from backend.models.pm import PM, Crew
from backend.models.settings import SystemSettings  # noqa: F401
from backend.models.email import EmailState  # noqa: F401
from backend.services import suggest as S
from backend.services import jn_booking as B

MON = date(2030, 11, 4)
TODAY = date(2030, 11, 1)  # the Friday before


class NoWeather:
    def blocked(self, job, day):
        return None


class RainOn:
    def __init__(self, day):
        self.day = day

    def blocked(self, job, day):
        return "rain" if day == self.day else None


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def setup(db, crews=(("DCT", ["roofing"], 1),), pms=("Luke Mroz",)):
    cs = [Crew(name=n, trades=t, rank=r, is_active=True) for n, t, r in crews]
    ps = [PM(name=n, is_active=True, baseline_capacity=3, max_capacity=5) for n in pms]
    db.add_all(cs + ps)
    db.commit()
    return cs, ps


def job(db, name, score=50.0, **kw):
    fields = {"bucket": "to_schedule", "primary_trade": "roofing", "ready_status": "clear", "duration_days": 1, **kw}
    j = Job(customer_name=name, address="1 Main St", score=score, **fields)
    db.add(j)
    db.commit()
    return j


def run(db, weather=None, pm_ids=None):
    return S.suggest_week(db, MON, pm_ids=pm_ids, today=TODAY, forecasts=weather or NoWeather())


def test_fills_mon_to_fri_best_score_first_one_build_per_crew_per_day(db):
    (crew,), (pm,) = setup(db)
    jobs = [job(db, f"Job {i}", score=s) for i, s in enumerate([10, 90, 50, 70, 30, 20])]
    out = run(db)
    got = {j.customer_name: j.suggested_date for j in jobs if j.suggested_date}
    assert got == {"Job 1": MON, "Job 3": date(2030, 11, 5), "Job 2": date(2030, 11, 6),
                   "Job 4": date(2030, 11, 7), "Job 5": date(2030, 11, 8)}
    assert out["waiting"] == 1
    assert all(j.planned_date is None for j in jobs)                 # nothing saved as a plan
    assert B.candidates(db) == []                                    # Push to JobNimbus ignores them
    assert jobs[1].suggested_crew_id == crew.id and jobs[1].suggested_pm_id == pm.id


def test_works_around_a_must_build_dragged_in_and_jobs_booked_in_jobnimbus(db):
    (crew,), (pm,) = setup(db)
    must = job(db, "Must build", score=1, planned_date=MON, planned_crew_id=1, planned_pm_id=1)
    must.days_estimate = {"eff": 80, "why": ["80 squares"]}           # a 2-day build: Mon and Tue
    booked = job(db, "Booked", bucket="scheduled", jn_start_date=date(2030, 11, 6), jn_crews=["DCT"])
    a = job(db, "A", score=90)
    db.commit()
    run(db)
    assert must.planned_date == MON and must.suggested_date is None  # left where it was
    assert booked.suggested_date is None
    assert a.suggested_date == date(2030, 11, 7)                     # Mon/Tue must-build, Wed booked


def test_must_build_jobs_go_first(db):
    setup(db)
    low = job(db, "Must", score=1, must_build=True)
    high = job(db, "High", score=99)
    run(db)
    assert low.suggested_date == MON and high.suggested_date == date(2030, 11, 5)


def test_skips_flagged_on_hold_planned_and_test_jobs(db):
    setup(db)
    flagged = job(db, "Flagged", ready_status="flagged")
    hold = job(db, "Hold", ready_status="hold")
    test = job(db, "TEST 3 Greg practice - Aaron Christy (ignore)")
    ok = job(db, "OK")
    run(db)
    assert [j.suggested_date for j in (flagged, hold, test)] == [None, None, None]
    assert ok.suggested_date == MON


def test_crews_only_get_their_trade_and_test_crews_are_never_used(db):
    setup(db, crews=(("Peoples Gutters", ["gutters"], 1), ("IRR Test Crew", ["roofing"], 1)))
    roof = job(db, "Roof")
    run(db)
    assert roof.suggested_date is None


def test_only_full_roofs_are_suggested(db):
    setup(db, crews=(("DCT", ["roofing"], 1), ("Peoples Gutters", ["gutters"], 2), ("Leon", ["siding"], 3)))
    roof = job(db, "Full roof", score=10)
    others = [job(db, n, score=90, primary_trade=t) for n, t in
              (("Repair", "roofing_repair"), ("Gutters", "gutters"), ("Siding", "siding"))]
    run(db)
    assert roof.suggested_date == MON
    assert all(o.suggested_date is None for o in others)


def test_a_multi_day_build_must_fit_inside_the_week(db):
    setup(db)
    big = job(db, "Big", score=90)
    big.days_estimate = {"eff": 130, "why": ["130 squares"]}          # 3 days
    fillers = [job(db, f"F{i}", score=80 - i) for i in range(4)]
    db.commit()
    run(db)
    assert big.suggested_date == MON and big.suggested_days == 3
    assert [f.suggested_date for f in fillers] == [date(2030, 11, 7), date(2030, 11, 8), None, None]


def test_no_build_dates_and_rain_move_a_job_to_another_day(db):
    setup(db)
    nb = job(db, "No Monday", score=90, no_build_dates=[{"start": "2030-11-04", "end": "2030-11-04", "reason": "away"}])
    other = job(db, "Other", score=10)
    run(db, weather=RainOn(date(2030, 11, 5)))
    assert other.suggested_date == MON
    assert nb.suggested_date == date(2030, 11, 6)                    # not Mon (asked), not Tue (rain)


def test_only_the_pms_picked_in_the_header_and_their_daily_max(db):
    _, (luke, other) = setup(db, crews=(("A", ["roofing"], 1), ("B", ["roofing"], 2)), pms=("Luke Mroz", "Brandon"))
    luke.max_capacity = 1
    db.commit()
    jobs = [job(db, f"J{i}", score=90 - i) for i in range(3)]
    run(db, pm_ids=[luke.id])
    assert {j.suggested_pm_id for j in jobs if j.suggested_date} == {luke.id}
    assert [j.suggested_date for j in jobs] == [MON, date(2030, 11, 5), date(2030, 11, 6)]  # one a day


def test_running_again_replaces_this_weeks_suggestions(db):
    setup(db)
    a = job(db, "A", score=90)
    run(db)
    a.ready_status = "flagged"
    db.commit()
    run(db)
    assert a.suggested_date is None


def test_keep_turns_a_suggestion_into_a_plan_and_clear_dismisses(db):
    setup(db)
    a, b = job(db, "A", score=90), job(db, "B", score=80)
    run(db)
    assert S.keep(db, [a.id], "Greg") == 1
    assert a.planned_date == MON and a.planned_crew_id and a.planned_pm_id and a.suggested_date is None
    assert [j.id for j in B.candidates(db)] == [a.id]               # now Push can send it
    assert S.clear(db, job_ids=[b.id]) == 1 and b.suggested_date is None and b.planned_date is None


def test_no_days_left_this_week(db):
    setup(db)
    job(db, "A")
    out = S.suggest_week(db, MON, today=date(2030, 11, 8), forecasts=NoWeather())
    assert out["suggested"] == [] and "No build days" in out["reason"]
