"""
Weather service — Two-stage architecture per spec §6:
  Stage 1: Open-Meteo (free API) — daily filtering, scoring pre-filter
  Stage 2: Clarity Wx / BamWx — final authority, night-before checks

Provider selection: If BAMWX_API_KEY is configured, Clarity Wx is primary.
Otherwise falls back to Open-Meteo. Both return a normalized forecast dict.
"""
import httpx
from datetime import datetime, date

from sqlalchemy.orm import Session

from backend.config import settings as app_settings
from backend.models.job import Job, JobBucket
from backend.models.settings import SystemSettings
from backend.services import claritywx


# Open-Meteo (Stage 1 — free, no API key needed)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return s.value if s else default


# ---------------------------------------------------------------------------
# Forecast retrieval — dual provider
# ---------------------------------------------------------------------------

def get_forecast(lat: float, lon: float, target_date: str | None = None) -> dict | None:
    """
    Get weather forecast — tries Clarity Wx first (if configured),
    falls back to Open-Meteo.  Returns normalized dict:
    { date, temp_max, temp_min, precipitation, wind_max, wind_gust,
      humidity, pop_am, pop_pm, tstorm_am, tstorm_pm, snow, ice, source }
    """
    # Try Clarity Wx (Stage 2) first
    if claritywx.is_configured():
        forecast = _get_claritywx_forecast(lat, lon, target_date)
        if forecast:
            return forecast

    # Fallback to Open-Meteo (Stage 1)
    return _get_openmeteo_forecast(lat, lon, target_date)


def _get_claritywx_forecast(lat: float, lon: float, target_date: str | None = None) -> dict | None:
    """Get forecast from Clarity Wx and normalize to our standard format."""
    daily = claritywx.get_daily_forecast(lat, lon)
    if not daily:
        return None

    target = target_date or date.today().isoformat()

    # Find matching day
    for day in daily:
        valid_at = day.get("validAt", "")
        # validAt may be full ISO datetime or just date — compare date portion
        if valid_at and valid_at[:10] == target:
            return claritywx.normalize_daily_forecast(day, target)

    # If target date not found, use first day
    if daily:
        return claritywx.normalize_daily_forecast(daily[0], target)

    return None


def _get_openmeteo_forecast(lat: float, lon: float, target_date: str | None = None) -> dict | None:
    """Get forecast from Open-Meteo (free) and normalize to our standard format."""
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
                "wind_gust": 0,  # Open-Meteo free tier doesn't provide gust
                "humidity": 0,   # Not available in free tier
                "pop_am": 0,
                "pop_pm": 0,
                "tstorm_am": 0,
                "tstorm_pm": 0,
                "snow": 0,
                "ice": 0,
                "dew_point": 0,
                "cloud_cover": 0,
                "source": "openmeteo",
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Material threshold checking — enhanced with Clarity Wx data
# ---------------------------------------------------------------------------

def check_material_thresholds(
    db: Session, material_type: str, forecast: dict,
    rain_window_result: dict | None = None,
) -> dict:
    """
    Check if weather conditions meet material-specific thresholds.
    Enhanced with humidity, rain window, thunderstorm, and snow/ice checks
    when Clarity Wx data is available.
    """
    mat = (material_type or "").lower()
    temp_min = forecast.get("temp_min", 0)
    temp_max = forecast.get("temp_max", 0)
    wind_max = forecast.get("wind_max", 0)
    wind_gust = forecast.get("wind_gust", 0)
    precip = forecast.get("precipitation", 0)
    humidity = forecast.get("humidity", 0)
    tstorm_am = forecast.get("tstorm_am", 0)
    tstorm_pm = forecast.get("tstorm_pm", 0)
    snow = forecast.get("snow", 0)
    ice = forecast.get("ice", 0)
    source = forecast.get("source", "unknown")

    # Get material-specific thresholds from settings
    threshold_map = {
        "asphalt": ("weather_asphalt_min_temp", "weather_asphalt_max_wind"),
        "polymer_modified": ("weather_polymer_min_temp", "weather_polymer_max_wind"),
        "tpo": ("weather_tpo_min_temp", "weather_tpo_max_wind"),
        "duro_last": ("weather_tpo_min_temp", "weather_tpo_max_wind"),
        "epdm": ("weather_tpo_min_temp", "weather_tpo_max_wind"),
        "coating": ("weather_coating_min_temp", "weather_coating_max_wind"),
        "wood_shake": ("weather_wood_shake_min_temp", "weather_wood_shake_max_wind"),
        "slate": ("weather_slate_min_temp", "weather_slate_max_wind"),
        "metal": ("weather_metal_min_temp", "weather_metal_max_wind"),
        "siding": ("weather_asphalt_min_temp", "weather_siding_max_wind"),
    }

    temp_key, wind_key = threshold_map.get(
        mat, ("weather_asphalt_min_temp", "weather_asphalt_max_wind")
    )
    min_temp_threshold = float(_get_setting(db, temp_key, "40"))
    max_wind_threshold = float(_get_setting(db, wind_key, "20"))

    issues = []

    # --- Core checks (all materials) ---
    if temp_min < min_temp_threshold:
        issues.append(f"Temp {temp_min}°F below {min_temp_threshold}°F threshold")
    if wind_max > max_wind_threshold:
        issues.append(f"Wind {wind_max}mph exceeds {max_wind_threshold}mph threshold")
    if precip > 0.1:
        issues.append(f"Precipitation: {precip} inches")

    # --- Gust check for siding (spec §6.5: gust matters more than sustained) ---
    if mat == "siding" and wind_gust > max_wind_threshold:
        issues.append(f"Wind gust {wind_gust}mph exceeds {max_wind_threshold}mph threshold")

    # --- Snow / ice (any material — hard stop) ---
    if snow > 0.1:
        issues.append(f"Snow: {snow} inches expected")
    if ice > 0:
        issues.append(f"Ice accumulation: {ice} inches")

    # --- Thunderstorm probability (Clarity Wx only) ---
    if source == "claritywx" and (tstorm_am > 50 or tstorm_pm > 50):
        issues.append(f"Thunderstorm risk: AM {tstorm_am}%, PM {tstorm_pm}%")

    # --- Humidity check for coatings (spec §6.5 line 279) ---
    if mat == "coating" and source == "claritywx":
        max_humidity = float(_get_setting(db, "weather_coating_max_humidity", "85"))
        if humidity > max_humidity:
            issues.append(f"Humidity {humidity}% exceeds {max_humidity}% threshold for coatings")

    # --- Multi-day rain window for TPO/EPDM and Coatings ---
    if rain_window_result and rain_window_result.get("rain_expected"):
        window_hrs = rain_window_result.get("hours_checked", 0)
        total_rain = rain_window_result.get("total_rain", 0)
        issues.append(
            f"Rain expected within {window_hrs}hr window: {total_rain} inches"
        )

    # --- Determine status ---
    if not issues:
        status = "clear"
        detail = (
            f"Conditions favorable: {temp_min}-{temp_max}°F, "
            f"wind {wind_max}mph, no precipitation"
        )
        if source == "claritywx":
            detail += f", humidity {humidity}%"
    elif len(issues) >= 2 or (precip > 0.1 and temp_min < min_temp_threshold) or snow > 0.1 or ice > 0:
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
        "source": source,
    }


# ---------------------------------------------------------------------------
# Job-level weather checks
# ---------------------------------------------------------------------------

def check_weather_for_job(
    db: Session, job_id: int, target_date: str | None = None,
    force_bamwx: bool = False,
) -> dict:
    """
    Check weather for a specific job.
    If force_bamwx=True, uses Clarity Wx even if not the default provider.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job not found"}
    if not job.latitude or not job.longitude:
        return {"error": "Job has no coordinates — geocoding needed"}

    # Get forecast
    if force_bamwx and claritywx.is_configured():
        forecast = _get_claritywx_forecast(job.latitude, job.longitude, target_date)
        if not forecast:
            forecast = get_forecast(job.latitude, job.longitude, target_date)
    else:
        forecast = get_forecast(job.latitude, job.longitude, target_date)

    if not forecast:
        return {"error": "Could not retrieve forecast"}

    # Check rain window for TPO/EPDM/Coatings (spec §6.5)
    rain_window_result = None
    mat = (job.material_type or "").lower()
    if mat in ("tpo", "duro_last", "epdm", "coating") and claritywx.is_configured():
        hours = 24 if mat in ("tpo", "duro_last", "epdm") else 48
        rain_window_result = claritywx.check_rain_window_hours(
            job.latitude, job.longitude, hours
        )

    result = check_material_thresholds(db, mat, forecast, rain_window_result)

    # Update job weather status
    job.weather_status = result["status"]
    job.weather_detail = result["detail"]
    db.commit()

    result["job_id"] = job.id
    result["customer_name"] = job.customer_name
    return result


def check_all_scheduled_jobs(db: Session) -> dict:
    """
    Check weather for all scheduled jobs.
    Auto-rollback: if a job gets "do_not_build", move it to Not Built
    with reason "Weather Pre-Build" and generate a weather rollback note.

    Returns: { results: [...], rolled_back: [...], scheduler_decision: [...] }
    """
    jobs = db.query(Job).filter(Job.bucket == JobBucket.SCHEDULED.value).all()
    results = []
    rolled_back = []
    needs_decision = []

    for job in jobs:
        target = str(job.date_scheduled) if job.date_scheduled else None
        result = check_weather_for_job(db, job.id, target)
        results.append(result)

        status = result.get("status")
        if status == "do_not_build":
            # Auto-rollback per spec §6.3 line 264
            _auto_rollback_job(db, job, result.get("detail", ""))
            rolled_back.append({
                "job_id": job.id,
                "customer_name": job.customer_name,
                "detail": result.get("detail", ""),
            })
        elif status == "scheduler_decision":
            needs_decision.append({
                "job_id": job.id,
                "customer_name": job.customer_name,
                "detail": result.get("detail", ""),
                "forecast": result.get("forecast"),
            })

    return {
        "results": results,
        "rolled_back": rolled_back,
        "scheduler_decision": needs_decision,
        "total_checked": len(jobs),
    }


def _auto_rollback_job(db: Session, job: Job, weather_detail: str):
    """
    Auto-move a scheduled job to Not Built due to weather.
    Spec §6.3: "Automatically moves job to Not Built. Pre-fills reason as Weather."
    """
    from backend.services.notes import generate_weather_rollback_note

    job.bucket = JobBucket.NOT_BUILT.value
    job.not_built_reason = "Weather Pre-Build"
    job.rescheduled_count += 1
    job.priority_bump += 5.0
    db.commit()

    # Generate weather rollback note (stored locally, pushed_to_jn=False)
    generate_weather_rollback_note(db, job, weather_detail)

    # Move back to to_schedule with elevated priority
    job.bucket = JobBucket.TO_SCHEDULE.value
    db.commit()


# ---------------------------------------------------------------------------
# Scheduler Decision — include or exclude a marginal job (spec §6.3 line 265)
# ---------------------------------------------------------------------------

def handle_scheduler_decision(db: Session, job_id: int, action: str) -> dict:
    """
    Handle scheduler's decision on a marginal weather job.
    action: "include" (override, keep scheduled) or "exclude" (move to not built)
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job not found"}

    from backend.services.notes import generate_weather_rollback_note

    if action == "exclude":
        _auto_rollback_job(db, job, f"Scheduler excluded: {job.weather_detail or 'marginal conditions'}")
        return {"action": "excluded", "job_id": job.id}
    elif action == "include":
        job.weather_status = "clear"
        job.weather_detail = f"Scheduler override: included despite marginal conditions. Original: {job.weather_detail}"
        db.commit()

        # Log the override as a note
        from backend.models.note_log import NoteLog
        note = NoteLog(
            job_id=job.id,
            jn_job_id=job.jn_job_id,
            note_type="weather_rollback",
            note_text=(
                f"[SCHEDULER SYSTEM -- {datetime.now().strftime('%B %d %Y %I:%M%p')}] "
                f"Weather override: Scheduler included job despite marginal conditions. "
                f"Original status: scheduler_decision. {job.customer_name}, {job.address}. "
                f"Note generated automatically by Indy Roof Scheduling System."
            ),
            pushed_to_jn=False,
        )
        db.add(note)
        db.commit()
        return {"action": "included", "job_id": job.id}
    else:
        return {"error": f"Invalid action: {action}"}
