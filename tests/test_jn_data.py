"""Parsing JobNimbus material orders and job/contact lookups (no network)."""
import pytest

from backend.emails import jn_data as J
from backend.emails.products import lookup_shingle

# Real material order lines from queued jobs (2026-10-03)
OAKRIDGE = {"name": "Owens Corning Oakridge Architectural Shingles",
            "color": "Owens Corning Oakridge Algae Resistant Driftwood 3 Bundle Per Square"}
HIGHLANDER = {"name": "Malarkey Roofing Highlander 242 Architectural Shingles 4 Bundles per Square",
              "color": "Malarkey Highlander AR Shingles 242 Black Oak 3 Bundles Per Square"}
VISTA = {"name": "Malarkey Roofing Vista AR 252 Architectural Shingles",
         "color": "Malarkey Roofing Products Vista Algae-Resistant 252 Brilliant Black 3 Bundles per Square"}
DURATION = {"name": "Owens Corning TruDefinition Duration Architectural Shingles",
            "color": "Owens Corning Trudefinition Duration Terracotta 3 Bundle Per Square"}
STARTER = {"name": "Malarkey Roofing Smart Start 210 Starter Shingles", "color": "Black"}
RIDGE = {"name": "Owens Corning ProEdge Hip & Ridge Shingles"}
APRON = {"name": "Quality Aluminum Gutter Apron ARA62", "color": "Quality Aluminum ARA62 2.5\" X 1.75\" Apron Black 200"}
SIDING = {"name": "CertainTeed Mainstreet Double 4\" x 12' 6\" Vinyl Lap Siding",
          "color": "CertainTeed Mainstreet D4\" Granite Gray 12 Pieces"}
J_CHANNEL = {"name": "CertainTeed 50303 J Channel", "color": "CertainTeed J-Channel 3/4\" Matte Autumn Red 5030323"}
TPO = {"name": "Carlisle 60 mil TPO Membrane 10' x 100'", "color": "White"}


@pytest.mark.parametrize("item,product,color", [
    (OAKRIDGE, "Owens Corning Oakridge", "Driftwood"),
    (HIGHLANDER, "Malarkey Highlander", "Black Oak"),
    (VISTA, "Malarkey Vista", "Brilliant Black"),
    (DURATION, "Owens Corning Duration", "Terracotta"),
])
def test_shingle_product_and_color(item, product, color):
    m = J.parse_materials([STARTER, RIDGE, APRON, item])
    assert lookup_shingle(m.shingle_line).display_name == product
    assert m.shingle_color == color
    assert not m.is_low_slope


def test_accessories_never_count_as_the_shingle():
    m = J.parse_materials([STARTER, RIDGE, APRON])
    assert m.shingle_line == "" and m.shingle_color == ""


def test_siding_product_and_color_skip_trim():
    m = J.parse_materials([J_CHANNEL, SIDING])
    assert m.siding_product == "CertainTeed Mainstreet"
    assert m.siding_color == "Granite Gray"


def test_low_slope_detected_from_membrane_without_shingles():
    assert J.parse_materials([TPO]).is_low_slope
    assert not J.parse_materials([TPO, OAKRIDGE]).is_low_slope  # mixed job: still a shingle roof


def test_messy_color_falls_back_to_blank():
    item = {"name": "Owens Corning Oakridge Shingles", "color": "see notes per HO request 2 tone w/ accent rows on dormers"}
    assert J.parse_materials([item]).shingle_color == ""


def test_newest_material_order_wins(monkeypatch):
    def fake_get(endpoint, params=None):
        return {"results": [
            {"date_created": 100, "items": [OAKRIDGE]},
            {"date_created": 200, "items": [HIGHLANDER]},  # re-order with the final choice
        ]}
    monkeypatch.setattr(J, "_jn_get", fake_get)
    m = J.parse_materials(J.fetch_material_items("j1"))
    assert lookup_shingle(m.shingle_line).display_name == "Malarkey Highlander"


def fake_jn(monkeypatch, job, contact, orders=(), activities=()):
    def fake_get(endpoint, params=None):
        if endpoint.startswith("jobs/"):
            return job
        if endpoint.startswith("contacts/"):
            return contact
        if endpoint == "v2/materialorders":
            return {"results": list(orders)}
        if endpoint == "activities":
            return {"count": len(activities), "activity": list(activities)}
        raise AssertionError(endpoint)
    monkeypatch.setattr(J, "_jn_get", fake_get)


def test_job_details_commercial_contact_and_start_date(monkeypatch):
    fake_jn(monkeypatch,
            {"record_type_name": "Commercial", "date_start": 1792000000, "primary": {"id": "c1"}},
            {"first_name": "JANE", "email": "jane@example.com", "mobile_phone": "(317) 555-0142"},
            orders=[{"items": [VISTA]}])
    d = J.fetch_job_details("j1")
    assert d.is_commercial is True and d.first_name == "Jane"
    assert d.customer_email == "jane@example.com" and d.customer_phone == "(317) 555-0142"
    assert d.start_date is not None and d.materials.shingle_color == "Brilliant Black"
    assert d.job_link == "https://app.jobnimbus.com/job/j1"


def test_residential_types_are_not_commercial(monkeypatch):
    for rt in ("Retail", "Insurance"):
        fake_jn(monkeypatch, {"record_type_name": rt, "primary": {"id": "c1"}}, {"first_name": "Pat"})
        assert J.fetch_job_details("j1").is_commercial is False


def test_lookup_failure_returns_blanks_not_an_error(monkeypatch):
    def boom(endpoint, params=None):
        raise RuntimeError("JobNimbus down")
    monkeypatch.setattr(J, "_jn_get", boom)
    d = J.fetch_job_details("j1")
    assert d.is_commercial is None and d.customer_email == "" and d.errors
    assert d.materials.shingle_line == ""


def test_jn_schedule_email_detection(monkeypatch):
    from datetime import datetime
    acts = [{"note": "<b>Project Update from Indy Roof & Restoration: J-1</b> Dear Jane", "date_created": 1790000000}]
    fake_jn(monkeypatch, {}, {}, activities=acts)
    assert J.jn_schedule_email_sent("j1", since=datetime.fromtimestamp(1790000000 - 60))
    assert not J.jn_schedule_email_sent("j1", since=datetime.fromtimestamp(1790000000 + 86400))
