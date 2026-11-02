from datetime import date, datetime, timedelta, timezone

from backend.services.rain_chance import INDY, rain_chance_words, sun_times

ZIONSVILLE = (39.9509, -86.2617)
MONDAY = date(2026, 11, 2)
NIGHT_BEFORE = datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)  # 8 PM Sunday in Indianapolis


def _hours(chances: dict[int, float], z: bool = True) -> list[dict]:
    """BAM-style hourly rows for Monday, 8 PM Sunday through 2 AM Tuesday (Indianapolis time)."""
    start = datetime(2026, 11, 1, 20, tzinfo=INDY)
    rows = []
    for i in range(30):
        t = start + timedelta(hours=i)
        stamp = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ("Z" if z else "")
        rows.append({"validAt": stamp, "pop": chances.get(t.hour, 0) if t.date() == MONDAY else 90})
    return rows


def test_sunrise_and_sunset_in_zionsville():
    rise, set_ = sun_times(*ZIONSVILLE, MONDAY)
    assert (rise.hour, set_.hour) == (7, 17) and 10 < rise.minute < 25 and 35 < set_.minute < 50


def test_only_daylight_hours_count():
    # 90% overnight and 80% at 6 AM and 7 PM: outside sunrise to sunset, so left out
    words = rain_chance_words(_hours({6: 80, 7: 30, 9: 20, 12: 30, 19: 80}), *ZIONSVILLE, MONDAY, NIGHT_BEFORE)
    assert words == "Up to 30% until 1 PM, then under 10% (sunrise 7:16 AM, sunset 5:43 PM)"


def test_dry_day_and_a_middle_shower():
    assert rain_chance_words(_hours({}), *ZIONSVILLE, MONDAY, NIGHT_BEFORE).startswith("Under 10% all day (")
    words = rain_chance_words(_hours({11: 40, 12: 60, 13: 55}), *ZIONSVILLE, MONDAY, NIGHT_BEFORE)
    assert words.startswith("Under 10% until 11 AM, then up to 40% from 11 AM to Noon, "
                            "then up to 60% from Noon to 2 PM, then under 10% (")


def test_times_without_a_zone_are_read_from_where_the_forecast_starts():
    hourly = _hours({8: 30}, z=False)
    assert rain_chance_words(hourly, *ZIONSVILLE, MONDAY, NIGHT_BEFORE).startswith("Under 10% until 8 AM, then up to 30%")


def test_nothing_to_say_without_hours():
    assert rain_chance_words(None, *ZIONSVILLE, MONDAY) == ""
    assert rain_chance_words(_hours({}), *ZIONSVILLE, date(2026, 11, 9), NIGHT_BEFORE) == ""
