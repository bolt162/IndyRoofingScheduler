"""Rep/PM contact list: only active team members are ever named in an email."""
from dataclasses import replace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.emails import team as T
from backend.emails.compose import compose
from backend.emails.preview import SAMPLES
from backend.models.email import TeamContact


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[TeamContact.__table__])
    session = sessionmaker(bind=engine)()
    T.seed_team(session)
    yield session
    session.close()


def with_rep(db, jn_name, sample="roof_vista"):
    return replace(SAMPLES[sample], **T.rep_contact(db, jn_name))


def test_seed_runs_once_and_keeps_edits(db):
    assert db.query(TeamContact).count() == len(T.DEFAULT_TEAM)
    row = db.query(TeamContact).filter_by(jn_name="Nick Smith").one()
    row.phone = "(317) 000-0000"
    db.commit()
    assert T.seed_team(db) == 0
    assert db.query(TeamContact).filter_by(jn_name="Nick Smith").one().phone == "(317) 000-0000"


def test_active_rep_appears_in_footer_and_referral(db):
    c = with_rep(db, "Nick Smith")
    assert "reach out to Nick Smith directly at (317) 435-7468" in compose("week_1", c).text
    assert "Send their name and number to Nick Smith" in compose("week_7", c).text


def test_name_matching_ignores_case_and_spacing(db):
    assert T.rep_contact(db, "  joe   VENN ")["rep_phone"] == "(317) 667-7119"


@pytest.mark.parametrize("former", ["Quincy Barrett", "Tim Russell", "Brandon Campbell", "Cody Osborne", "Someone New"])
def test_former_or_unknown_rep_is_never_named(db, former):
    c = with_rep(db, former)
    first = former.split()[0]
    for key in ("welcome", "week_1", "week_7", "rotation"):
        assert first not in compose(key, c).text
    assert "call or text us at (317) 886-7436. We're always happy to help." in compose("week_1", c).text
    assert "Send their name and number to our office" in compose("week_7", c).text


def test_rep_marked_inactive_drops_out(db):
    row = db.query(TeamContact).filter_by(jn_name="Paul Sopke").one()
    row.is_active = False
    db.commit()
    assert T.rep_contact(db, "Paul Sopke") == {"rep_name": "", "rep_phone": "", "rep_email": ""}


def test_rep_without_phone_falls_back_to_office(db):
    row = db.query(TeamContact).filter_by(jn_name="Lavell Chestnut").one()
    assert row.phone == "(317) 752-7003"
    row.phone = None
    db.commit()
    c = with_rep(db, "Lavell Chestnut", sample="roof_repair")
    assert c.rep_name == "Lavell Chestnut" and c.rep_phone == ""
    leak = compose("rotation", c).text
    assert "please call us at (317) 886-7436" in leak and "Lavell" not in leak
    assert "Lavell" not in compose("week_1", with_rep(db, "Lavell Chestnut")).text


def test_pm_is_luke_mroz_and_not_a_rep(db):
    pms = T.active_pms(db)
    assert [p.display_name for p in pms] == ["Luke Mroz"]
    assert pms[0].email == "luke.mroz@indyroofandrestoration.com"
    assert T.rep_contact(db, "Luke Mroz")["rep_name"] == ""


def test_normalize_phone():
    assert T.normalize_phone("3176677119") == "(317) 667-7119"
    assert T.normalize_phone("317-435-7468") == "(317) 435-7468"
    assert T.normalize_phone("12") is None


def test_customers_see_jimmy_and_sherilyn(db):
    assert T.rep_contact(db, "James Clinger")["rep_name"] == "Jimmy Clinger"
    assert T.rep_contact(db, "Sherilyn Nowak")["rep_name"] == "Sherilyn Nowak"
    assert "reach out to Jimmy Clinger directly at (463) 867-2451" in compose("week_1", with_rep(db, "James Clinger")).text



def test_full_preview_goes_to_aaron_greg_and_luke(db):
    assert sorted(T.full_preview_recipients(db)) == [
        "aaron@indyroofandrestoration.com",
        "greg.russell@indyroofandrestoration.com",
        "luke.mroz@indyroofandrestoration.com",
    ]


def test_reps_get_their_own_preview_but_ops_and_owner_are_never_named_to_customers(db):
    assert T.rep_email_for(db, "Nick Smith") == "nick.smith@indyroofandrestoration.com"
    assert T.rep_email_for(db, "Quincy Barrett") == ""
    for name in ("Greg Russell", "Aaron Christy"):
        assert T.rep_contact(db, name)["rep_name"] == ""
