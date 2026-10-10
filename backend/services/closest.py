"""
"Closest jobs only" lookup.

Given one roofing or siding job, list the other jobs waiting on that same trade,
sorted purely by distance. Score, must-build, PM capacity, weather and every
other ranking factor are ignored on purpose. This is a read-only view: it does
not change scores, clusters or the build plan.
"""
from sqlalchemy.orm import Session

from backend.models.job import Job, JobBucket
from backend.services.clustering import get_driving_distances_batch, haversine_miles

# Trades this view supports. Repairs are their own trades and are not mixed in.
CLOSEST_TRADES = ("roofing", "siding")

# Only jobs still waiting to be scheduled are candidates.
SCHEDULABLE_BUCKETS = (JobBucket.TO_SCHEDULE.value, JobBucket.OTHER_TRADES.value)

# Straight-line pre-filter before asking Google for driving miles (one 1 x N call).
DRIVING_CANDIDATES = 25


def open_trades(job: Job) -> list[str]:
    """Trades this job is still waiting on.

    To Schedule: the primary trade. Other Trades: the secondary trades not yet complete.
    """
    if job.bucket == JobBucket.TO_SCHEDULE.value:
        return [job.primary_trade] if job.primary_trade else []
    if job.bucket == JobBucket.OTHER_TRADES.value:
        status = job.secondary_trades_status or {}
        return [t for t in (job.secondary_trades or []) if status.get(t) != "complete"]
    return []


def closest_trade_for(job: Job) -> str | None:
    """The roofing/siding trade to match on for this job, or None if it has neither open."""
    for trade in open_trades(job):
        if trade in CLOSEST_TRADES:
            return trade
    return None


def _job_row(job: Job, miles: float) -> dict:
    return {
        "job_id": job.id,
        "customer_name": job.customer_name,
        "address": job.address,
        "lat": job.latitude,
        "lng": job.longitude,
        "miles": round(miles, 1),
        "bucket": job.bucket,
        "score": job.score,
        "must_build": job.must_build,
        "standalone_rule": job.standalone_rule,
    }


def find_closest_jobs(db: Session, anchor: Job, limit: int = 10, trade: str | None = None) -> dict:
    """Return the `limit` nearest same-trade jobs to `anchor`, nearest first.

    Raises ValueError with a plain-English message when the job can't be used.
    """
    trade = trade or closest_trade_for(anchor)
    if trade not in CLOSEST_TRADES:
        raise ValueError("Closest jobs only works for roofing or siding jobs that are waiting to be scheduled.")
    if not (anchor.latitude and anchor.longitude):
        raise ValueError("This job has no map location from JobNimbus, so distances can't be measured.")

    candidates = [
        j for j in db.query(Job).filter(
            Job.bucket.in_(SCHEDULABLE_BUCKETS),
            Job.id != anchor.id,
            Job.latitude != None,  # noqa: E711
            Job.longitude != None,  # noqa: E711
        ).all()
        if trade in open_trades(j)
    ]

    origin = (anchor.latitude, anchor.longitude)
    straight = sorted(
        ((haversine_miles(origin[0], origin[1], j.latitude, j.longitude) * 1.3, j) for j in candidates),
        key=lambda pair: pair[0],
    )
    shortlist = straight[:max(limit, DRIVING_CANDIDATES)]

    # Origins list has only the anchor at index 0; destinations put the anchor at 0 too
    # so the batch helper's "skip i == j" rule only skips anchor-to-itself.
    dests = [origin] + [(j.latitude, j.longitude) for _, j in shortlist]
    driving = get_driving_distances_batch([origin], dests)

    ranked = []
    all_driving = True
    for idx, (est_miles, job) in enumerate(shortlist, start=1):
        miles = driving.get((0, idx))
        if miles is None:
            miles = est_miles
            all_driving = False
        ranked.append((miles, job))
    ranked.sort(key=lambda pair: pair[0])

    return {
        "anchor": _job_row(anchor, 0.0),
        "trade": trade,
        "distance_source": "driving" if all_driving else "estimated",
        "total_candidates": len(candidates),
        "jobs": [_job_row(job, miles) for miles, job in ranked[:limit]],
    }
