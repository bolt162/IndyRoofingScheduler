"""
Weather service — Stage 1 (OpenWeatherMap free API).
Stage 2 (BamWx) will be added in Phase 3.
"""
import httpx
from datetime import datetime, date

from sqlalchemy.orm import Session

from backend.models.job import Job, JobBucket
from backend.models.settings import SystemSettings


# Using Open-Meteo (completely free, no API key needed) instead of OpenWeatherMap
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return s.value if s else default


def get_forecast(lat: float, lon: float, target_date: str | None = None) -> dict | None:
    """Get weather forecast from Open-Meteo API (free, no key required)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Indiana/Indianapolis",
        "forecast_days": 7,
    }

    try:
        resp = httpx.get(OPEN_METEO_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])

        # Find the target date or use first available
        target = target_date or date.today().isoformat()
        idx = 0
        for i, d in enumerate(dates):
            if d == target:
                idx = i
                break

        if idx < len(dates):
            return {
                "date": dates[idx],
                "temp_max": daily["temperature_2m_max"][idx],
                "temp_min": daily["temperature_2m_min"][idx],
                "precipitation": daily["precipitation_sum"][idx],
                "wind_max": daily["wind_speed_10m_max"][idx],
            }
    except Exception:
        pass
    return None


def check_material_thresholds(db: Session, material_type: str, forecast: dict) -> dict:
    """Check if weather conditions meet material-specific thresholds."""
    mat = (material_type or "").lower()
    temp_min = forecast.get("temp_min", 0)
    wind_max = forecast.get("wind_max", 0)
    precip = forecast.get("precipitation", 0)

    # Get material-specific thresholds from settings
    threshold_map = {
        "asphalt": ("weather_asphalt_min_temp", "weather_asphalt_max_wind"),
        "polymer_modified": ("weather_polymer_min_temp", "weather_polymer_max_wind"),
        "tpo": ("weather_tpo_min_temp", "weather_tpo_max_wind"),
        "duro_last": ("weather_tpo_min_temp", "weather_tpo_max_wind"),
        "epdm": ("weather_tpo_min_temp", "weather_tpo_max_wind"),
        "coating": ("weather_coating_min_temp", "weather_coating_max_wind"),
        "siding": ("weather_asphalt_min_temp", "weather_siding_max_wind"),
    }

    temp_key, wind_key = threshold_map.get(mat, ("weather_asphalt_min_temp", "weather_asphalt_max_wind"))
    min_temp_threshold = float(_get_setting(db, temp_key, "40"))
    max_wind_threshold = float(_get_setting(db, wind_key, "20"))

    issues = []
    if temp_min < min_temp_threshold:
        issues.append(f"Temp {temp_min}°F below {min_temp_threshold}°F threshold")
    if wind_max > max_wind_threshold:
        issues.append(f"Wind {wind_max}mph exceeds {max_wind_threshold}mph threshold")
    if precip > 0:
        issues.append(f"Precipitation: {precip} inches")

    if not issues:
        status = "clear"
        detail = f"Conditions favorable: {temp_min}-{forecast.get('temp_max', 0)}°F, wind {wind_max}mph, no precipitation"
    elif len(issues) >= 2 or (precip > 0.1 and temp_min < min_temp_threshold):
        status = "do_not_build"
        detail = "Do not build: " + "; ".join(issues)
    else:
        status = "scheduler_decision"
        detail = "Marginal conditions: " + "; ".join(issues)

    return {
        "status": status,
        "detail": detail,
        "forecast": forecast,
        "issues": issues,
    }


def check_weather_for_job(db: Session, job_id: int, target_date: str | None = None) -> dict:
    """Check weather for a specific job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job not found"}
    if not job.latitude or not job.longitude:
        return {"error": "Job has no coordinates — geocoding needed"}

    forecast = get_forecast(job.latitude, job.longitude, target_date)
    if not forecast:
        return {"error": "Could not retrieve forecast"}

    result = check_material_thresholds(db, job.material_type or "", forecast)

    # Update job weather status
    job.weather_status = result["status"]
    job.weather_detail = result["detail"]
    db.commit()

    return result


def check_all_scheduled_jobs(db: Session) -> list[dict]:
    """Check weather for all scheduled jobs."""
    jobs = db.query(Job).filter(Job.bucket == JobBucket.SCHEDULED.value).all()
    results = []
    for job in jobs:
        result = check_weather_for_job(db, job.id, str(job.date_scheduled) if job.date_scheduled else None)
        result["job_id"] = job.id
        result["customer_name"] = job.customer_name
        results.append(result)
    return results
