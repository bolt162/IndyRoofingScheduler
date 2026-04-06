"""
Clarity Wx (BamWx) API client — Stage 2 weather intelligence.
Provides hyper-local construction weather forecasts via the Clarity Wx API.
Used as the "final authority" for scheduling decisions per spec §6.3.

Auth: GET /session?key=...&secret=... → JWT token
Endpoints: /future-daily, /future-hourly, /current-conditions
"""
import time
import httpx
from backend.config import settings

# In-memory session token cache
_token_cache: dict = {"token": None, "expires_at": 0}


def is_configured() -> bool:
    """Check if Clarity Wx credentials are available."""
    return bool(settings.BAMWX_API_KEY and settings.BAMWX_API_SECRET)


def _get_session_token() -> str | None:
    """Get or refresh the Clarity Wx session token."""
    if not is_configured():
        return None

    # Use cached token if still valid (refresh 5 min before expiry)
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 300:
        return _token_cache["token"]

    try:
        base = settings.BAMWX_BASE_URL.rstrip("/")
        resp = httpx.get(
            f"{base}/session",
            params={"key": settings.BAMWX_API_KEY, "secret": settings.BAMWX_API_SECRET},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success", True):
            return None

        token = data.get("api-token") or data.get("apiToken")
        if token:
            # Cache for 1 hour (conservative — JWT may last longer)
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + 3600
            return token
    except Exception:
        pass
    return None


def _api_get(endpoint: str, params: dict) -> dict | None:
    """Make an authenticated GET request to Clarity Wx API.
    Auth uses cookies — the /session endpoint sets an api-token cookie."""
    token = _get_session_token()
    if not token:
        return None

    base = settings.BAMWX_BASE_URL.rstrip("/")
    cookies = {"api-token": token}

    try:
        resp = httpx.get(f"{base}{endpoint}", params=params, cookies=cookies, timeout=20)

        # If 401, clear cache and retry once
        if resp.status_code == 401:
            _token_cache["token"] = None
            _token_cache["expires_at"] = 0
            token = _get_session_token()
            if not token:
                return None
            cookies = {"api-token": token}
            resp = httpx.get(f"{base}{endpoint}", params=params, cookies=cookies, timeout=20)

        resp.raise_for_status()
        data = resp.json()
        if data.get("success") is False:
            return None
        return data
    except Exception:
        return None


def get_daily_forecast(lat: float, lon: float) -> list[dict] | None:
    """
    Get 10-day daily forecast from Clarity Wx.
    Returns list of daily forecast objects with fields:
    validAt, tmin, tmax, rain, rh, windSpeed, windGust, popAm, popPm,
    tstormAm, tstormPm, snow, ice, dewPoint, cloudCover, iconCode, etc.
    """
    data = _api_get("/future-daily", {
        "lat": str(lat),
        "lon": str(lon),
        "unit": "imperial",
    })
    if data:
        return data.get("dailyForecast", [])
    return None


def get_hourly_forecast(lat: float, lon: float) -> list[dict] | None:
    """
    Get 30-hour hourly forecast from Clarity Wx.
    Returns list of hourly forecast objects with fields:
    validAt, temp2m, rh2m, windSpeed, windGust, rainAccum, pop,
    tstormProb, snowAccum, iceAccum, visibility, etc.
    """
    data = _api_get("/future-hourly", {
        "lat": str(lat),
        "lon": str(lon),
        "unit": "imperial",
    })
    if data:
        return data.get("hourlyForecast", [])
    return None


def get_current_conditions(lat: float, lon: float) -> dict | None:
    """Get current weather conditions from Clarity Wx."""
    return _api_get("/current-conditions", {
        "lat": str(lat),
        "lon": str(lon),
        "unit": "imperial",
    })


def get_utilization() -> dict | None:
    """Check API usage — does not count toward monthly limit."""
    return _api_get("/account/utilization/current", {})


def normalize_daily_forecast(day: dict, target_date: str | None = None) -> dict:
    """
    Normalize a Clarity Wx daily forecast object to our standard format
    (same shape as Open-Meteo output for drop-in compatibility).
    """
    return {
        "date": day.get("validAt", target_date or ""),
        "temp_max": day.get("tmax", 0),
        "temp_min": day.get("tmin", 0),
        "precipitation": day.get("rain", 0),
        "wind_max": day.get("windSpeed", 0),
        "wind_gust": day.get("windGust", 0),
        "humidity": day.get("rh", 0),
        "pop_am": day.get("popAm", 0),
        "pop_pm": day.get("popPm", 0),
        "tstorm_am": day.get("tstormAm", 0),
        "tstorm_pm": day.get("tstormPm", 0),
        "snow": day.get("snow", 0),
        "ice": day.get("ice", 0),
        "dew_point": day.get("dewPoint", 0),
        "cloud_cover": day.get("cloudCover", 0),
        "source": "claritywx",
    }


def check_rain_window_hours(lat: float, lon: float, hours: int) -> dict:
    """
    Check if rain is expected in the next N hours using hourly forecast.
    Used for TPO (24hr) and Coatings (48hr) rain window requirements.

    Returns: { "rain_expected": bool, "total_rain": float, "rain_hours": list[str] }
    """
    hourly = get_hourly_forecast(lat, lon)
    if not hourly:
        return {"rain_expected": False, "total_rain": 0, "rain_hours": [], "source": "unavailable"}

    # Only check up to the requested window
    window = hourly[:min(hours, len(hourly))]
    total_rain = 0.0
    rain_hours = []

    for h in window:
        accum = h.get("rainAccum", 0) or 0
        if accum > 0:
            total_rain += accum
            rain_hours.append(h.get("validAt", "?"))

    return {
        "rain_expected": total_rain > 0.01,  # Trace amounts ignored
        "total_rain": round(total_rain, 3),
        "rain_hours": rain_hours,
        "hours_checked": len(window),
        "source": "claritywx_hourly",
    }
