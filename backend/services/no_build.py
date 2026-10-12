"""
No-Build Dates — date ranges a customer asked us not to build (a wedding, a trip,
a family event). The scheduler treats them as a hard block, like a bad forecast.

Stored on the job as a JSON list:
    [{"start": "2026-10-20", "end": "2026-10-27", "reason": "Wedding"}]
Both ends are inclusive. Windows that have already ended are ignored everywhere
and dropped the next time the job's dates are saved, so they clear themselves.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Indiana/Indianapolis")
MAX_REASON_LEN = 200


def local_today() -> date:
    """Today in Indianapolis (the server runs in UTC)."""
    return datetime.now(LOCAL_TZ).date()


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def active_windows(windows: list | None, today: date | None = None) -> list[dict]:
    """Windows that haven't ended yet, sorted by start date. Malformed entries are skipped."""
    today = today or local_today()
    result = []
    for w in windows or []:
        if not isinstance(w, dict):
            continue
        start, end = _as_date(w.get("start")), _as_date(w.get("end"))
        if not start or not end or end < start or end < today:
            continue
        result.append({"start": start.isoformat(), "end": end.isoformat(),
                       "reason": (w.get("reason") or "").strip() or None})
    return sorted(result, key=lambda w: (w["start"], w["end"]))


def clean_windows(windows: list[dict], today: date | None = None) -> list[dict]:
    """Validate windows before saving. Raises ValueError if an end date is before its start."""
    for w in windows:
        start, end = _as_date(w.get("start")), _as_date(w.get("end"))
        if not start or not end:
            raise ValueError("Every No-Build window needs a start date and an end date.")
        if end < start:
            raise ValueError(f"End date {end:%b %-d} is before start date {start:%b %-d}.")
        if w.get("reason"):
            w["reason"] = str(w["reason"])[:MAX_REASON_LEN]
    return active_windows(windows, today)


def find_conflict(windows: list | None, start: date, duration_days: int = 1) -> dict | None:
    """The first active window a build starting on `start` would touch, or None.
    A multi-day build occupies `duration_days` calendar days from its start."""
    start = _as_date(start)
    if not start:
        return None
    last = start + timedelta(days=max(duration_days or 1, 1) - 1)
    for w in active_windows(windows):
        if date.fromisoformat(w["start"]) <= last and date.fromisoformat(w["end"]) >= start:
            return w
    return None


def job_conflict(job, start: date, duration_days: int | None = None) -> dict | None:
    return find_conflict(job.no_build_dates, start, duration_days or job.duration_days or 1)


def describe(window: dict) -> str:
    """'Oct 20 to Oct 27 (Wedding)' — for office-facing messages."""
    start, end = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
    span = f"{start:%b %-d}" if start == end else f"{start:%b %-d} to {end:%b %-d}"
    return f"{span} ({window['reason']})" if window.get("reason") else span
