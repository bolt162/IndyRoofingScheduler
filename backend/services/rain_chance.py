"""
Rain chance for the hours crews can build, sunrise to sunset at the job (Aaron, 2026-11-01).

BAM's hourly forecast gives a chance of rain for each hour; the weather email shows it as one short
line per build, e.g. "Up to 30% until 1 PM, then under 10%". Sunrise and sunset come from NOAA's
sunrise equation (within a couple of minutes, no API needed).
"""
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

INDY = ZoneInfo("America/Indiana/Indianapolis")
_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)


def sun_times(lat: float, lon: float, day: date) -> tuple[datetime, datetime]:
    """(sunrise, sunset) at that spot on that day, Indianapolis time."""
    jstar = day.toordinal() - date(2000, 1, 1).toordinal() + 0.0008 - lon / 360
    m = math.radians((357.5291 + 0.98560028 * jstar) % 360)
    c = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    transit = jstar + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    dec = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    phi = math.radians(lat)
    half = math.degrees(math.acos((math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(dec))
                                  / (math.cos(phi) * math.cos(dec)))) / 360
    return tuple((_J2000 + timedelta(days=transit + d)).astimezone(INDY) for d in (-half, half))


def _clock(t: datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def _hour(h: int) -> str:
    return "Noon" if h == 12 else f"{(h - 1) % 12 + 1} {'AM' if h < 12 else 'PM'}"


def _local_hours(hourly: list[dict], now: datetime) -> list[tuple[datetime, float]]:
    """BAM's hours as (Indianapolis time, chance). Times without a zone are read as UTC or local,
    whichever puts the first hour closest to now (the forecast starts at the current hour)."""
    parsed = []
    for h in hourly:
        try:
            parsed.append((datetime.fromisoformat(str(h.get("validAt", "")).replace("Z", "+00:00")),
                           h.get("pop") or 0))
        except ValueError:
            continue
    if not parsed:
        return []
    if parsed[0][0].tzinfo is None:
        first = parsed[0][0]
        as_utc = abs(first.replace(tzinfo=timezone.utc) - now)
        as_local = abs(first.replace(tzinfo=INDY) - now)
        zone = timezone.utc if as_utc <= as_local else INDY
        parsed = [(t.replace(tzinfo=zone), p) for t, p in parsed]
    return [(t.astimezone(INDY), p) for t, p in parsed]


def _band(p: float) -> int:
    return 0 if p < 10 else 1 if p < 50 else 2


def _fill_dips(bands: list[int]) -> list[int]:
    """A lull of 1 or 2 hours inside a wetter stretch takes the stretch's band, so the line stays short.
    Spikes are never smoothed away."""
    out = bands[:]
    for size in (1, 2):
        for i in range(1, len(out) - size):
            before, after = out[i - 1], out[i + size]
            if before == after and all(b < before for b in out[i:i + size]):
                out[i:i + size] = [before] * size
    return out


def rain_chance_words(hourly: list[dict] | None, lat: float, lon: float, day: date,
                      now: datetime | None = None) -> str:
    """e.g. "Up to 30% until 1 PM, then under 10% (sunrise 7:21 AM, sunset 5:33 PM)".
    Empty when BAM has no hours for that day's daylight."""
    if not hourly:
        return ""
    sunrise, sunset = sun_times(lat, lon, day)
    hours = [(t, p) for t, p in _local_hours(hourly, now or datetime.now(timezone.utc))
             if t.date() == day and sunrise.hour <= t.hour <= sunset.hour]
    if not hours:
        return ""
    segments = []  # [band, start hour, end hour, highest chance]
    for (t, p), band in zip(hours, _fill_dips([_band(p) for _, p in hours])):
        if segments and segments[-1][0] == band:
            segments[-1][2], segments[-1][3] = t.hour + 1, max(segments[-1][3], p)
        else:
            segments.append([band, t.hour, t.hour + 1, p])
    parts = []
    for i, (band, start, end, top) in enumerate(segments):
        label = "under 10%" if band == 0 else f"up to {top:.0f}%"
        if len(segments) == 1:
            parts.append(f"{label} all day")
        elif i == 0:
            parts.append(f"{label} until {_hour(end)}")
        elif i == len(segments) - 1:
            parts.append(f"then {label}")
        else:
            parts.append(f"then {label} from {_hour(start)} to {_hour(end)}")
    words = ", ".join(parts)
    return f"{words[0].upper()}{words[1:]} (sunrise {_clock(sunrise)}, sunset {_clock(sunset)})"
