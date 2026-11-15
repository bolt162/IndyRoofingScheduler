"""Settings the timers read at startup. A bad value here used to stop every timer, so each one is checked on save
and falls back to its default on read."""

HHMM_KEYS = {"weather_morning_check_time": "06:00", "bamwx_check_time": "20:00"}
MINUTES_KEYS = {"jn_sync_interval_minutes": 30}


def parse_hhmm(value) -> tuple[int, int] | None:
    """'6:30' or '06:30' -> (6, 30). Anything else -> None."""
    try:
        h, m = str(value).strip().split(":")
        if not (h.isdigit() and m.isdigit() and len(m) == 2):
            return None
        h, m = int(h), int(m)
        return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None
    except ValueError:
        return None


def parse_minutes(value) -> int | None:
    """A whole number of minutes, 1 to 1440. Anything else -> None."""
    s = str(value).strip()
    return int(s) if s.isdigit() and 1 <= int(s) <= 1440 else None


def clean(key: str, value: str) -> str | None:
    """The value to save for a timer setting, or None if it is not valid. Other keys pass through unchanged."""
    if key in HHMM_KEYS:
        hm = parse_hhmm(value)
        return f"{hm[0]:02d}:{hm[1]:02d}" if hm else None
    if key in MINUTES_KEYS:
        n = parse_minutes(value)
        return str(n) if n else None
    return value


PROBLEM = {
    "weather_morning_check_time": "Enter the time as hours and minutes on a 24-hour clock, for example 06:00.",
    "bamwx_check_time": "Enter the time as hours and minutes on a 24-hour clock, for example 20:00.",
    "jn_sync_interval_minutes": "Enter a whole number of minutes from 1 to 1440, for example 30.",
}
