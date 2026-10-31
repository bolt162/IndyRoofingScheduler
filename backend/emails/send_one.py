"""
Send one customer this week's queue email now: the same email Thursday's run would pick for them.
For catching up a customer who missed one. Counts as their weekly email, so Thursday won't repeat it.

On the server:  railway ssh --service scheduler -- python -m backend.emails.send_one 26675
"""
import sys
from datetime import datetime

from backend.database import SessionLocal
from backend.emails import runner as R


def send_one(db, jn_number: str, now: datetime | None = None, mode: str | None = None) -> dict:
    rc = R.RunContext(db, now or datetime.utcnow(), mode)
    want = jn_number.removeprefix("J-")
    plans = [p for p in R.plan_weekly(rc) if (p.job.jn_number or "").removeprefix("J-") == want]
    if not plans:
        return {"sent": 0, "why": "job not in the build queue"}
    if not plans[0].email:
        return {"sent": 0, "why": plans[0].decision.reason}
    return {**R._send_planned(rc, plans), "subject": plans[0].email.subject, "mode": rc.mode}


if __name__ == "__main__":
    session = SessionLocal()
    try:
        print(send_one(session, sys.argv[1]))
    finally:
        session.close()
