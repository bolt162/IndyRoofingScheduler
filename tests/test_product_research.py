"""Unknown-product research rule. Uses a fake Claude client; nothing calls the real API."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.emails import research as R
from backend.emails.compose import compose
from backend.emails.preview import SAMPLES
from backend.emails.products import lookup_shingle, product_key
from backend.models.email import ProductClassification


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ProductClassification.__table__])
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def _resp(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    """Mimics client.beta.messages.create (research) and client.messages.create (extraction)."""
    def __init__(self, research_text="GAF says Timberline AS II is Class 4, SBS polymer modified. https://gaf.com/as2",
                 extracted=None, research_stops=("end_turn",)):
        self.extracted = extracted or {
            "manufacturer": "GAF", "product_line": "Timberline AS II", "impact_class": "class_4",
            "composition": "polymer_modified", "confidence": "high",
            "summary": "UL 2218 Class 4, SBS modified.",
            "sources": [{"url": "https://www.gaf.com/en-us/as2", "title": "GAF spec sheet"}],
        }
        self.research_calls = []
        self.stops = list(research_stops)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._research))
        self.messages = SimpleNamespace(create=self._extract)

    def _research(self, **kw):
        self.research_calls.append(kw)
        stop = self.stops.pop(0) if self.stops else "end_turn"
        return _resp("partial" if stop == "pause_turn" else "GAF Timberline AS II: Class 4, SBS. https://gaf.com/as2", stop)

    def _extract(self, **kw):
        self.extract_kwargs = kw
        return _resp(json.dumps(self.extracted))


GAF_LINE = "GAF Timberline AS II Shingles (GAF Timberline AS II Charcoal 3 Bundles Per Square)"


# --- Confirmed table entries (Aaron, 2026-10-03) ---

def test_oakridge_is_oxidized_no_rating_no_flag():
    info = lookup_shingle("Owens Corning Oakridge Architectural Shingles")
    assert info.impact_class is None and info.composition == "oxidized" and info.week2_version == "C"
    email = compose("week_2", replace(SAMPLES["roof_vista"], shingle_line="Owens Corning Oakridge"))
    assert "impact rating" not in email.text and not email.flags


def test_duration_class3_oxidized_vs_highlander_class3_polymer():
    duration = lookup_shingle("Owens Corning TruDefinition Duration Architectural Shingles")
    highlander = lookup_shingle("Malarkey Roofing Highlander 242 Architectural Shingles")
    assert duration.impact_class == highlander.impact_class == 3
    assert duration.composition == "oxidized"
    assert highlander.composition == "polymer_modified"


def test_material_order_names_match_table():
    assert lookup_shingle("Malarkey Roofing Vista AR 252 Architectural Shingles").display_name == "Malarkey Vista"


def test_product_key_ignores_color_and_bundles():
    a = product_key("GAF Timberline HDZ Shingles (GAF Timberline HDZ Charcoal 3 Bundles Per Square)")
    b = product_key("GAF Timberline HDZ Shingles (GAF Timberline HDZ Pewter Gray)")
    assert a == b == "gaf timberline hdz shingles"


# --- Unknown product flow ---

def test_unknown_product_creates_research_row_and_flags(db):
    info, flag = R.resolve_product(db, GAF_LINE, job_id=7)
    assert info is None and flag
    row = db.query(ProductClassification).one()
    assert row.status == "new" and row.first_job_id == 7
    R.resolve_product(db, GAF_LINE.replace("Charcoal", "Pewter"))
    assert db.query(ProductClassification).count() == 1  # same line, different color


WEAK = {"manufacturer": "GAF", "product_line": "Timberline AS II", "impact_class": "class_4",
        "composition": "polymer_modified", "confidence": "medium", "summary": "Class 4 per a retailer page.",
        "sources": [{"url": "https://www.homedepot.com/p/gaf-as2", "title": "Retailer"}]}


def test_thorough_research_is_approved_automatically(db):
    R.resolve_product(db, GAF_LINE)
    row = R.run_pending_research(db, client=FakeClient())[0]
    assert row.status == "approved" and row.reviewed_by == R.AUTO_REVIEWER
    info, flag = R.resolve_product(db, GAF_LINE)
    assert not flag and info.week2_version == "A"
    assert "approved automatically" in R.review_summary(row)


@pytest.mark.parametrize("change", [
    {"confidence": "medium"},
    {"impact_class": "unknown"},
    {"composition": "unknown"},
    {"sources": [{"url": "https://www.homedepot.com/p/x", "title": "Retailer"}]},
    {"sources": []},
])
def test_anything_less_than_thorough_waits_for_review(db, change):
    R.resolve_product(db, GAF_LINE)
    extracted = {**FakeClient().extracted, **change}
    row = R.run_pending_research(db, client=FakeClient(extracted=extracted))[0]
    assert row.status == "pending_review"
    assert R.resolve_product(db, GAF_LINE) == (None, True)
    assert "waiting for approval" in R.review_summary(row)


def test_manufacturer_source_matching():
    assert R.cites_manufacturer("GAF", [{"url": "https://www.gaf.com/en-us/roofing-products/x"}])
    assert R.cites_manufacturer("IKO Industries", [{"url": "https://www.iko.com/na/x"}])
    assert R.cites_manufacturer("Owens Corning", [{"url": "https://www.owenscorning.com/en-us/roofing"}])
    assert R.cites_manufacturer("Pabco", [{"url": "https://www.pabcoroofing.com/products"}])
    assert not R.cites_manufacturer("GAF", [{"url": "https://gaf.com.example.net/x"}])
    assert not R.cites_manufacturer("GAF", [{"url": "https://www.homedepot.com/gaf"}])


def test_research_then_pending_until_approved(db):
    R.resolve_product(db, GAF_LINE)
    client = FakeClient(extracted=WEAK)
    ready = R.run_pending_research(db, client=client)
    row = ready[0]
    assert row.status == "pending_review"
    assert row.display_name == "GAF Timberline AS II" and row.impact_class == 4
    assert row.composition == "polymer_modified"
    assert "homedepot.com" in json.loads(row.sources)[0]["url"]
    # research used web tools; extraction used structured output and no tools
    call = client.research_calls[0]
    assert {t["name"] for t in call["tools"]} == {"web_search", "web_fetch"}
    assert call["fallbacks"] == "default"
    assert client.extract_kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "tools" not in client.extract_kwargs

    # Still not used in emails until approved
    info, flag = R.resolve_product(db, GAF_LINE)
    assert info is None and flag

    R.review(db, row.id, approve=True, reviewer="aaron@indyroofandrestoration.com")
    info, flag = R.resolve_product(db, GAF_LINE)
    assert not flag and info.impact_class == 4 and info.week2_version == "A"
    email = compose("week_2", replace(SAMPLES["roof_vista"], shingle_line=GAF_LINE, product=info))
    assert "GAF Timberline AS II shingles carry a Class 4 impact rating" in email.text


def test_office_can_correct_before_approving(db):
    R.resolve_product(db, GAF_LINE)
    row = R.run_pending_research(db, client=FakeClient(extracted=WEAK))[0]
    R.review(db, row.id, approve=True, reviewer="office", impact_class=None)
    info, _ = R.resolve_product(db, GAF_LINE)
    assert info.impact_class is None and info.week2_version == "C"


def test_office_can_override_an_auto_approval(db):
    R.resolve_product(db, GAF_LINE)
    row = R.run_pending_research(db, client=FakeClient())[0]
    R.review(db, row.id, approve=True, reviewer="office", impact_class=3)
    assert R.resolve_product(db, GAF_LINE)[0].week2_version == "B"


def test_rejected_product_stays_generic(db):
    R.resolve_product(db, GAF_LINE)
    row = R.run_pending_research(db, client=FakeClient(extracted=WEAK))[0]
    R.review(db, row.id, approve=False, reviewer="office")
    info, flag = R.resolve_product(db, GAF_LINE)
    assert info is None and flag


def test_unknown_findings_are_recorded_not_guessed(db):
    R.resolve_product(db, GAF_LINE)
    extracted = {"manufacturer": "GAF", "product_line": "Timberline AS II", "impact_class": "unknown",
                 "composition": "unknown", "confidence": "low", "summary": "No spec sheet found.", "sources": []}
    row = R.run_pending_research(db, client=FakeClient(extracted=extracted))[0]
    assert row.impact_class is None and row.composition is None
    assert "Could not confirm: impact_class, composition" in row.summary


def test_pause_turn_is_continued(db):
    R.resolve_product(db, GAF_LINE)
    client = FakeClient(research_stops=("pause_turn", "end_turn"))
    R.run_pending_research(db, client=client)
    assert len(client.research_calls) == 2
    assert client.research_calls[1]["messages"][1]["role"] == "assistant"


def test_research_failure_retries_then_stops(db):
    R.resolve_product(db, GAF_LINE)

    class Boom(FakeClient):
        def _research(self, **kw):
            raise RuntimeError("API down")
    for _ in range(R.MAX_ATTEMPTS + 2):
        R.run_pending_research(db, client=Boom())
    row = db.query(ProductClassification).one()
    assert row.status == "research_failed" and row.research_attempts == R.MAX_ATTEMPTS
    # Customer emails are unaffected: still generic, still flagged
    assert R.resolve_product(db, GAF_LINE) == (None, True)


def test_refusal_is_a_failure_not_a_guess(db):
    R.resolve_product(db, GAF_LINE)
    R.run_pending_research(db, client=FakeClient(research_stops=("refusal",)))
    assert db.query(ProductClassification).one().status == "research_failed"


def test_review_summary_for_office():
    row = ProductClassification(raw_text=GAF_LINE, display_name="GAF Timberline AS II", impact_class=4,
                                composition="polymer_modified", confidence="high", summary="Class 4.",
                                sources=json.dumps([{"url": "https://gaf.com/as2", "title": "x"}]))
    text = R.review_summary(row)
    assert "Class 4, polymer modified" in text and "https://gaf.com/as2" in text
