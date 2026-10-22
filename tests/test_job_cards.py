"""Job cards show the JobNimbus job number and days in the build queue."""
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.email import EmailState
from backend.models.job import Job
from backend.routers.jobs import _enrich_with_latest_note
from backend.services.jobnimbus import map_jn_job_to_model


def test_sync_keeps_the_job_number():
    assert map_jn_job_to_model({"name": "Jenn Golding - J-26426", "number": "26426"})["jn_number"] == "26426"
    assert map_jn_job_to_model({"name": "No number"})["jn_number"] is None


def test_card_gets_the_date_it_entered_the_queue():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    job = Job(customer_name="Chris", address="1 Main St", jn_number="25000")
    db.add(job)
    db.commit()
    assert _enrich_with_latest_note(job, db)["entered_queue_at"] is None
    db.add(EmailState(job_id=job.id, mode="test", entered_queue_at=datetime(2026, 1, 1)))
    db.add(EmailState(job_id=job.id, mode="live", entered_queue_at=datetime(2026, 9, 1)))
    db.commit()
    out = _enrich_with_latest_note(job, db)
    assert out["entered_queue_at"] == datetime(2026, 9, 1)
    assert out["jn_number"] == "25000"
