"""'Closest jobs only' view: same trade, sorted by distance, ignores score."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.main as main
from backend.database import Base, get_db
from backend.models.job import Job
from backend.services import closest as C
from backend.services.auth import ClerkUser, get_approved_user

# Anchor ~1 hour north of Indy (Kokomo area); the others step further away.
ANCHOR = (40.4864, -86.1336)


def _job(db, name, lat, lng, trade="roofing", bucket="to_schedule", score=0.0, **kw):
    job = Job(customer_name=name, address=f"{name} St", latitude=lat, longitude=lng,
              primary_trade=trade, bucket=bucket, score=score, rescheduled_count=0, **kw)
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def env(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(main, "SessionLocal", Session)
    # No Google key in tests: force straight-line estimates
    monkeypatch.setattr(C, "get_driving_distances_batch", lambda o, d: {})

    def db_override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    user = ClerkUser({"sub": "u1", "email": "office@indyroofandrestoration.com", "approved": "true", "admin": "false"})
    main.app.dependency_overrides[get_db] = db_override
    main.app.dependency_overrides[get_approved_user] = lambda: user
    yield TestClient(main.app), Session
    main.app.dependency_overrides.clear()


def test_sorts_by_distance_and_ignores_score(env):
    client, Session = env
    db = Session()
    anchor = _job(db, "Anchor", *ANCHOR, must_build=True)
    far_high_score = _job(db, "Far", 39.77, -86.16, score=99)
    near_low_score = _job(db, "Near", 40.49, -86.14, score=1)
    middle = _job(db, "Middle", 40.30, -86.10, score=50)
    ids = (anchor.id, near_low_score.id, middle.id, far_high_score.id)
    db.close()

    r = client.get(f"/api/jobs/{ids[0]}/closest")
    assert r.status_code == 200
    body = r.json()
    assert body["trade"] == "roofing"
    assert body["distance_source"] == "estimated"
    assert [j["job_id"] for j in body["jobs"]] == list(ids[1:])
    miles = [j["miles"] for j in body["jobs"]]
    assert miles == sorted(miles)


def test_only_same_trade_and_waiting_jobs(env):
    client, Session = env
    db = Session()
    anchor = _job(db, "Anchor", *ANCHOR, trade="siding")
    siding = _job(db, "Siding", 40.48, -86.13, trade="siding")
    _job(db, "Roof", 40.48, -86.13, trade="roofing")
    _job(db, "SidingRepair", 40.48, -86.13, trade="siding_repair")
    _job(db, "Scheduled", 40.48, -86.13, trade="siding", bucket="scheduled")
    # Roof done, siding still open -> counts as a siding job
    open_sec = _job(db, "RoofDoneSidingOpen", 40.50, -86.13, bucket="other_trades",
                    secondary_trades=["siding"], secondary_trades_status={"siding": "pending"})
    # Roof done, siding already complete -> not a candidate
    _job(db, "SidingDone", 40.48, -86.13, bucket="other_trades",
         secondary_trades=["siding"], secondary_trades_status={"siding": "complete"})
    ids = {anchor.id, siding.id, open_sec.id}
    anchor_id = anchor.id
    db.close()

    body = client.get(f"/api/jobs/{anchor_id}/closest").json()
    assert {j["job_id"] for j in body["jobs"]} == ids - {anchor_id}


def test_limit_and_rejects_other_trades(env):
    client, Session = env
    db = Session()
    anchor = _job(db, "Anchor", *ANCHOR)
    for i in range(5):
        _job(db, f"J{i}", 40.4 - i * 0.05, -86.13)
    gutter = _job(db, "Gutters", 40.48, -86.13, trade="gutters")
    no_geo = _job(db, "NoGeo", None, None)
    ids = anchor.id, gutter.id, no_geo.id
    db.close()

    assert len(client.get(f"/api/jobs/{ids[0]}/closest?limit=3").json()["jobs"]) == 3
    assert client.get(f"/api/jobs/{ids[1]}/closest").status_code == 400
    assert client.get(f"/api/jobs/{ids[2]}/closest").status_code == 400
    assert client.get("/api/jobs/99999/closest").status_code == 404


def test_prefers_driving_miles_when_google_answers(env, monkeypatch):
    client, Session = env
    db = Session()
    anchor = _job(db, "Anchor", *ANCHOR)
    a = _job(db, "StraightNear", 40.49, -86.14)
    b = _job(db, "StraightFar", 40.40, -86.13)
    ids = anchor.id, a.id, b.id
    db.close()
    # Google says the straight-line-near one is a long drive (river, no bridge)
    monkeypatch.setattr(C, "get_driving_distances_batch", lambda o, d: {(0, 1): 30.0, (0, 2): 8.0})

    body = client.get(f"/api/jobs/{ids[0]}/closest").json()
    assert body["distance_source"] == "driving"
    assert [j["job_id"] for j in body["jobs"]] == [ids[2], ids[1]]
