"""Roof material and squares from JobNimbus: the order fills a blank material box, never a picked one."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.job import Job
from backend.models.settings import SystemSettings  # noqa: F401
from backend.models.email import EmailState  # noqa: F401
from backend.services import material_fill as M
from backend.services.jobnimbus import map_jn_job_to_model

HIGHLANDER = [{"name": "Malarkey Roofing Highlander 242 Architectural Shingles 4 Bundle Per Square"}]
OAKRIDGE = [{"name": "Owens Corning Oakridge Architectural Shingles (Owens Corning Oakridge Driftwood)"}]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def run(db, monkeypatch, jn_box, items, bucket="to_schedule", trade="roofing"):
    j = Job(customer_name="Test", address="1 Main St", jn_job_id="jn1", bucket=bucket, primary_trade=trade,
            duration_days=1)
    db.add(j)
    db.commit()
    puts = []
    monkeypatch.setattr(M, "fetch_material_items", lambda jnid: items)
    monkeypatch.setattr(M, "_jn_put", lambda endpoint, body: puts.append(body))
    M.fill(db, [(j, bucket, {"Roof Material Type": jn_box})])
    return j, puts


def test_blank_box_gets_polymer_modified_from_a_highlander_order(db, monkeypatch):
    j, puts = run(db, monkeypatch, "", HIGHLANDER)
    assert puts == [{"cf_string_9": "Polymer Modified"}] and j.material_type == "polymer_modified"


def test_old_brand_answer_is_replaced_by_the_order(db, monkeypatch):
    j, puts = run(db, monkeypatch, "OC", OAKRIDGE)
    assert puts == [{"cf_string_9": "Asphalt"}] and j.material_type == "asphalt"


@pytest.mark.parametrize("box,items,bucket,trade", [
    ("Metal", HIGHLANDER, "to_schedule", "roofing"),       # a person picked it
    ("", [], "to_schedule", "roofing"),                    # no order yet
    ("", HIGHLANDER, "primary_completed", "roofing"),      # already built
    ("", HIGHLANDER, "to_schedule", "siding"),             # not a roof
])
def test_leaves_it_alone(db, monkeypatch, box, items, bucket, trade):
    _, puts = run(db, monkeypatch, box, items, bucket, trade)
    assert puts == []


@pytest.mark.parametrize("box,expected", [
    ("Polymer Modified", "polymer_modified"), ("Asphalt", "asphalt"), ("Malarkey", "polymer_modified"),
    ("OC", None), ("PVC", "duro_last"), ("Modbit", "modbit"), ("TPO", "tpo"), ("Slate Tile", "slate"), ("", None),
])
def test_greg_s_material_options(box, expected):
    assert map_jn_job_to_model({"Roof Material Type": box})["material_type"] == expected


def test_second_material_box_and_square_count():
    m = map_jn_job_to_model({"Roof Material Type 2": "Polymer Modified", "Square Count": 28, "Roof Total Square": 0})
    assert m["material_type"] == "polymer_modified" and m["square_footage"] == 2800
    assert map_jn_job_to_model({"Roof Total Square": 19})["square_footage"] == 1900  # older field still read
