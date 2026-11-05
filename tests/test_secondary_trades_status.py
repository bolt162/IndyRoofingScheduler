"""JobNimbus renamed "Other Trades" to "Scheduling Secondary Trades" and added "All Trades Scheduled" (Nov 4 2026).
Some workflows still use "Other Trades", so all three must land in the same tab."""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.job import Job
from backend.models.email import JobEvent
from backend.models.settings import SystemSettings  # noqa: F401
from backend.services import jobnimbus as JN
from backend.services import suggest as S

NAMES = ["Other Trades", "Scheduling Secondary Trades", "All Trades Scheduled"]


@pytest.mark.parametrize("name", NAMES)
def test_every_secondary_trades_status_is_pulled_into_the_secondary_trades_tab(name):
    assert name in JN.TRACKED_JN_STATUSES  # pulled by the sync, so it is never archived
    mapped = JN.map_jn_job_to_model({"jnid": "abc", "status_name": name, "name": "Pat Doe - J-1"})
    assert mapped["bucket"] == "other_trades"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    yield session
    session.close()


def test_coming_back_from_archived_keeps_the_original_roof_done_wait(db):
    j = Job(customer_name="Pat", address="1 Main St", bucket="other_trades", primary_trade="roofing",
            jn_work_orders=[{"trade": "Roofing", "status": "Completed"}, {"trade": "Gutters", "status": "New"}])
    db.add(j)
    db.commit()
    db.add_all([
        JobEvent(job_id=j.id, from_bucket="scheduled", to_bucket="other_trades", created_at=datetime(2026, 10, 15)),
        # The rename made the sync archive the job, then the fix brought it back
        JobEvent(job_id=j.id, from_bucket="other_trades", to_bucket="archived", created_at=datetime(2026, 11, 4)),
        JobEvent(job_id=j.id, from_bucket="archived", to_bucket="other_trades", created_at=datetime(2026, 11, 5)),
    ])
    db.commit()
    assert S._waiting_days(db, j, date(2026, 11, 5)) == 21
