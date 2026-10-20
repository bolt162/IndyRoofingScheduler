"""Suggested build days from work order labor lines, and approve-first crew notes."""
import json
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.job import Job
from backend.models.pm import Crew
from backend.models.settings import SystemSettings
from backend.services import build_days as BD
from backend.services import crew_notes as CN
from backend.services import schedule_sync as SS


def roof(*labor, note=""):
    return {"number": "WO-1", "trade": "Roofing", "status": "New", "labor": [list(x) for x in labor],
            "customer_note": note}


def gutters(*labor):
    return {"number": "WO-2", "trade": "Gutters", "status": "New", "labor": [list(x) for x in labor]}


TEAR = "Tear off and Install Laminated Shingles"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


# --- build days ---

def test_a_typical_roof_is_one_day():
    est = BD.estimate([roof((TEAR, 24), ("Install Hip and Ridge Shingles", 120))])
    assert BD.days_for(est["eff"]) == 1 and est["why"] == ["24 squares"]


def test_a_big_steep_roof_is_two_days_and_says_why():
    est = BD.estimate([roof((TEAR, 43), ("Steep Fee - 12/12 - 19/12  Pitch", 10), ("Install Skylight", 1))])
    assert BD.days_for(est["eff"]) == 2
    assert est["why"] == ["43 squares", "12/12 or steeper", "1 skylight"]


def test_a_very_large_steep_two_story_roof_is_three_days():
    est = BD.estimate([roof((TEAR, 83), ("Steep Fee - 12/12 - 19/12  Pitch", 30), ("High charge - 2 story", 83))])
    assert BD.days_for(est["eff"]) == 3


def test_the_smaller_crew_gets_more_time():
    est = BD.estimate([roof((TEAR, 45), ("High charge - 2 story", 45))])  # 49.5 effective
    assert BD.days_for(est["eff"]) == 1
    assert BD.days_for(est["eff"], "A&M") == 2


def test_decking_layers_and_trim_add_time():
    plain = BD.estimate([roof((TEAR, 40))])["eff"]
    heavy = BD.estimate([roof((TEAR, 40), ("Remove extra layers of shingles", 40), ("Install OSB 7/12 or less", 30),
                              ("Cut-In & Install Trim", 1))])
    assert heavy["eff"] == plain + 6 + 4 + 4
    assert "extra layer to tear off" in heavy["why"] and "30 sheets of decking" in heavy["why"]


def test_no_work_order_falls_back_to_the_roof_report_squares_or_nothing():
    assert BD.estimate([], 30)["why"] == ["30 squares (no work order yet)"]
    assert BD.estimate([gutters(("6 Gutter Install - 1st Story", 100))]) is None


def test_suggestion_names_the_small_crew():
    job = SimpleNamespace(days_estimate=BD.estimate([roof((TEAR, 45), ("High charge - 2 story", 45))]))
    assert BD.suggestion(job, "A&M") == {"days": 2, "why": "45 squares, 2 story, A&M is a smaller crew"}
    assert BD.suggestion(SimpleNamespace(days_estimate=None)) is None


def test_the_sync_keeps_each_work_orders_labor_lines():
    wos = SS.summarize_work_orders([{"number": "WO-1", "record_type_name": "Roofing", "status_name": "New",
                                     "is_active": True, "items": [{"name": TEAR, "quantity": 22}, {"name": ""}]}])
    assert wos[0]["labor"] == [[TEAR, 22]]


# --- gutter scope ---

@pytest.mark.parametrize("wos, says", [
    ([roof((TEAR, 20)), gutters(("6 Gutter Install - 1st Story", 120), ("3 x 4 Downspout - 1st Story", 40))],
     "Full gutter replacement"),
    ([roof((TEAR, 20)), gutters(("Gutter Guard Install - Standard Guard", 85))], "only gutter guards added"),
    ([roof((TEAR, 20))], "Gutters are NOT being replaced. Protect the gutters."),
    ([roof((TEAR, 20), ("Remove Gutters", 1))], "Full gutter replacement"),
])
def test_gutter_scope_comes_from_the_work_orders(wos, says):
    assert says in CN.gutter_line(wos)["text"]


def test_gutter_guards_to_detach_are_mentioned_and_no_roof_means_no_line():
    assert "Detach and reset the gutter guards" in CN.gutter_line([roof((TEAR, 20), ("Detach Gutter Guards", 1))])["text"]
    assert CN.gutter_line([gutters(("6 Gutter Install - 1st Story", 1))]) is None


# --- AI suggestions ---

class FakeAI:
    def __init__(self, notes):
        self.notes, self.prompts = notes, []
        self.messages = self

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        text = json.dumps({"notes": self.notes})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def queued(db, **kw):
    fields = dict(customer_name="Test", address="1 Main", bucket="to_schedule", primary_trade="roofing",
                  jn_work_orders=[roof((TEAR, 24), note="House only")],
                  ready_input="[Oct 19 Pat, Note] Dog in the backyard, keep the gate closed")
    job = Job(**{**fields, **kw})
    db.add(job)
    db.commit()
    return job


def test_suggestions_have_the_gutter_line_then_quoted_notes(db):
    job = queued(db)
    ai = FakeAI([{"text": "Keep the backyard gate closed, there's a dog.", "quote": "Dog in the backyard",
                  "source": "Note by Pat, Oct 19"},
                 {"text": "Something with no quote", "quote": ""}])
    assert CN.run(db, client=ai)["refreshed"] == 1
    db.refresh(job)
    assert [s["kind"] for s in job.crew_note_suggestions] == ["gutters", "notes"]
    assert job.crew_note_suggestions[1]["quote"] == "Dog in the backyard"
    # The AI is told what the crew already has, so it doesn't repeat it
    assert "House only" in ai.prompts[0]
    # Nothing changed: the next sync doesn't ask again
    assert CN.run(db, client=ai)["refreshed"] == 0 and len(ai.prompts) == 1


def test_no_gutter_line_when_the_work_order_already_talks_about_gutters(db):
    job = queued(db, jn_work_orders=[roof((TEAR, 24), note="House only\nWe are replacing gutters")])
    CN.refresh(job, client=FakeAI([]))
    assert job.crew_note_suggestions == []


def test_lines_already_on_the_work_order_are_not_suggested(db):
    job = queued(db, jn_work_orders=[roof((TEAR, 24), note="Gutters are NOT being replaced. Protect the gutters.")])
    CN.refresh(job, client=FakeAI([]))
    assert job.crew_note_suggestions == []


def test_switched_off_means_no_suggestions(db):
    job = queued(db)
    db.add(SystemSettings(key=CN.SETTING_KEY, value="false"))
    db.commit()
    ai = FakeAI([])
    assert CN.run(db, client=ai) == {"enabled": False}
    assert ai.prompts == [] and job.crew_note_suggestions is None


def test_ai_failure_tries_again_next_sync(db):
    job = queued(db)

    class Broken:
        messages = SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert CN.run(db, client=Broken())["failed"] == 1
    assert job.crew_notes_hash is None


def test_approved_lines_are_added_once_to_the_crew_box():
    assert CN.merged_customer_note("House only", ["Full gutter replacement on this job.", "House only"]) == \
        "House only\n\nFull gutter replacement on this job."
    assert CN.merged_customer_note("", ["Keep the gate closed."]) == "Keep the gate closed."
    assert CN.merged_customer_note("Keep the gate closed.", ["keep the  gate closed."]) is None


def test_approve_cleans_and_records_who(db):
    job = queued(db)
    CN.approve(db, job, ["  Keep the gate closed. ", "", "Keep the gate closed."], "Greg Russell")
    assert job.crew_notes_approved == ["Keep the gate closed."] and job.crew_notes_by == "Greg Russell"


# --- the push uses both ---

def test_push_books_the_suggested_days_and_adds_approved_crew_notes(db, monkeypatch):
    from tests.test_jn_booking import FakeJN, planned_job, BUILD
    from backend.services import jn_booking as B
    monkeypatch.setenv("JN_BOOKING_MODE", "live")
    job = planned_job(db)
    job.days_estimate = BD.estimate([roof((TEAR, 43), ("Steep Fee - 12/12 - 19/12  Pitch", 10))])  # 2 days
    job.crew_notes_approved = ["Full gutter replacement on this job."]
    db.commit()
    jn = FakeJN()
    jn.wo["customer_note"] = "House only"
    result = B.push(db, "Greg", jn=jn, ai_client=FakeAI([]))
    assert result["booked"] == 1, result
    wo_put = jn.writes()[0][2]
    assert wo_put["all_day_start_date"] == BUILD.isoformat() and wo_put["all_day_end_date"] == "2030-10-30"
    assert wo_put["customer_note"] == "House only\n\nFull gutter replacement on this job."


def test_days_picked_on_the_card_win_and_notes_stay_off_when_switched_off(db, monkeypatch):
    from tests.test_jn_booking import FakeJN, planned_job
    from backend.services import jn_booking as B
    monkeypatch.setenv("JN_BOOKING_MODE", "live")
    job = planned_job(db)
    job.days_estimate = BD.estimate([roof((TEAR, 43), ("Steep Fee - 12/12 - 19/12  Pitch", 10))])
    job.planned_days = 3
    job.crew_notes_approved = ["Keep the gate closed."]
    db.add(SystemSettings(key=CN.SETTING_KEY, value="false"))
    db.commit()
    jn = FakeJN()
    B.push(db, "Greg", jn=jn)
    wo_put = jn.writes()[0][2]
    assert wo_put["all_day_end_date"] == "2030-10-31" and "customer_note" not in wo_put
    preview = B.preview(db)["items"]
    assert preview == [] or preview[0]["crew_notes"] is None


def test_lines_from_any_crew_work_order_are_not_repeated(db):
    # The crew's work order has no tear-off line, but its notes are still what the crew already reads
    wos = [{"number": "WO-9", "trade": "Roofing", "status": "New", "labor": [["Roofing Labor", 1]],
            "customer_note": "HOUSE ROOF ONLY\nContact PM before removing any decking"}]
    job = queued(db, jn_work_orders=wos)
    ai = FakeAI([{"text": "Call the PM before removing decking.", "quote": "Contact PM before removing any decking",
                  "source": "Work order WO-9"},
                 {"text": "Leave the copper for the homeowner.", "quote": "Leave it there for the homeowner",
                  "source": "Note by Greg"}])
    CN.refresh(job, client=ai)
    assert [s["text"] for s in job.crew_note_suggestions] == [
        "Gutters are NOT being replaced. Protect the gutters.", "Leave the copper for the homeowner."]
    assert "HOUSE ROOF ONLY" in ai.prompts[0]


def test_siding_jobs_ask_for_the_siding_crew_and_skip_the_gutter_line(db):
    job = queued(db, primary_trade="siding",
                 jn_work_orders=[roof((TEAR, 20)), {"number": "WO-3", "trade": "Siding", "labor": [], "customer_note": ""}])
    ai = FakeAI([])
    CN.refresh(job, client=ai)
    assert "SIDING crew" in ai.prompts[0] and job.crew_note_suggestions == []
