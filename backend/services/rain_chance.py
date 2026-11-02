"""
Rain chance for the hours crews can build, sunrise to sunset at the job (Aaron, 2026-11-01).

BAM's hourly forecast gives a chance of rain for each hour; the weather email shows each build's day as
blocks of hours with the same chance, e.g. "7 AM to 10 AM: 0%" then "10 AM to Noon: 10%". Sunrise and sunset come from NOAA's
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


def rain_chance_words(hourly: list[dict] | None, lat: float, lon: float, day: date,
                      now: datetime | None = None) -> str:
    """Blocks of hours with the same chance, one per line, e.g.
    "7 AM to 10 AM: 0%\n10 AM to Noon: 10%\n... \nSunrise 7:16 AM, sunset 5:43 PM" (Aaron, 2026-11-02).
    Chances are rounded to the nearest 10% so small wobbles don't split a block.
    Empty when BAM has no hours for that day's daylight."""
    if not hourly:
        return ""
    sunrise, sunset = sun_times(lat, lon, day)
    hours = [(t, p) for t, p in _local_hours(hourly, now or datetime.now(timezone.utc))
             if t.date() == day and sunrise.hour <= t.hour <= sunset.hour]
    if not hours:
        return ""
    blocks = []  # [chance, start hour, end hour]
    for t, p in hours:
        chance = int(p / 10 + 0.5) * 10
        if blocks and blocks[-1][0] == chance:
            blocks[-1][2] = t.hour + 1
        else:
            blocks.append([chance, t.hour, t.hour + 1])
    lines = [f"{_hour(start)} to {_hour(end)}: {chance}%" for chance, start, end in blocks]
    return "\n".join(lines + [f"Sunrise {_clock(sunrise)}, sunset {_clock(sunset)}"])
