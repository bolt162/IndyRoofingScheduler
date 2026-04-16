from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Default settings to seed on first run
DEFAULT_SETTINGS = {
    # PM capacity
    "pm_baseline_capacity": {"value": "3", "description": "Default builds per PM per day"},
    "pm_max_capacity": {"value": "5", "description": "Hard ceiling builds per PM per day"},

    # Distance thresholds (miles)
    "cluster_tier_1_miles": {"value": "1", "description": "Tight cluster - up to 5 builds"},
    "cluster_tier_2_miles": {"value": "2", "description": "Close cluster - up to 4 builds"},
    "cluster_tier_3_miles": {"value": "10", "description": "Standard range - baseline 3 builds"},
    "cluster_tier_4_miles": {"value": "25", "description": "Extended range - 1-2 builds"},
    "cluster_tier_5_miles": {"value": "40", "description": "Outlier - standalone rule triggered"},

    # Weather thresholds - asphalt
    "weather_asphalt_min_temp": {"value": "40", "description": "Min temp (F) for asphalt shingles"},
    "weather_asphalt_max_wind": {"value": "20", "description": "Max wind (mph) for asphalt shingles"},
    "weather_asphalt_rain": {"value": "false", "description": "Allow rain for asphalt (false=no rain)"},

    # Weather thresholds - polymer modified
    "weather_polymer_min_temp": {"value": "20", "description": "Min temp (F) for polymer modified"},
    "weather_polymer_max_wind": {"value": "20", "description": "Max wind (mph) for polymer modified"},

    # Weather thresholds - TPO/EPDM
    "weather_tpo_min_temp": {"value": "40", "description": "Min temp (F) for TPO/EPDM"},
    "weather_tpo_max_wind": {"value": "15", "description": "Max wind (mph) for TPO/EPDM"},
    "weather_tpo_rain_window_hrs": {"value": "24", "description": "Hours of no rain required for TPO/EPDM"},

    # Weather thresholds - coatings
    "weather_coating_min_temp": {"value": "50", "description": "Min temp (F) for coatings"},
    "weather_coating_rain_window_hrs": {"value": "48", "description": "Hours of no rain required for coatings"},

    # Weather thresholds - siding
    "weather_siding_max_wind": {"value": "15", "description": "Max wind (mph) for siding"},

    # Weather thresholds - wood shake (spec §6.5 line 280)
    "weather_wood_shake_min_temp": {"value": "40", "description": "Min temp (F) for wood shake"},
    "weather_wood_shake_max_wind": {"value": "20", "description": "Max wind (mph) for wood shake"},

    # Weather thresholds - slate
    "weather_slate_min_temp": {"value": "40", "description": "Min temp (F) for slate"},
    "weather_slate_max_wind": {"value": "20", "description": "Max wind (mph) for slate"},

    # Weather thresholds - metal
    "weather_metal_min_temp": {"value": "40", "description": "Min temp (F) for metal"},
    "weather_metal_max_wind": {"value": "15", "description": "Max wind (mph) for metal — more sensitive"},

    # Coatings - humidity threshold (spec §6.5 line 279)
    "weather_coating_max_humidity": {"value": "85", "description": "Max humidity (%) for coatings"},
    "weather_coating_max_wind": {"value": "15", "description": "Max wind (mph) for coatings"},

    # Automated weather check times
    "weather_morning_check_time": {"value": "06:00", "description": "Morning weather check time (24hr format)"},

    # Secondary trade aging
    "secondary_aging_yellow_days": {"value": "7", "description": "Days after primary complete — warning flag (secondary trades overdue)"},
    "secondary_aging_red_days": {"value": "10", "description": "Days after primary complete — ESCALATED (higher urgency, $ floating)"},

    # AI rules
    "ai_custom_rules": {"value": "", "description": "Plain-English rules applied to every scoring run"},

    # Scoring weights (0-100)
    "weight_days_in_queue": {"value": "25", "description": "Weight for days in queue vs average"},
    "weight_payment_type": {"value": "20", "description": "Weight for payment type priority"},
    "weight_trade_complexity": {"value": "10", "description": "Weight for single vs multi-trade"},
    "weight_proximity": {"value": "15", "description": "Weight for geographic clustering"},
    "weight_material_weather": {"value": "10", "description": "Weight for material-weather compatibility"},
    "weight_permit_confirmed": {"value": "5", "description": "Weight for permit confirmed bonus"},
    "weight_duration_confirmed": {"value": "5", "description": "Weight for duration confirmed bonus"},
    "weight_rescheduled": {"value": "10", "description": "Weight for rescheduled counter bump"},

    # BamWx
    "bamwx_check_time": {"value": "20:00", "description": "Night-before BamWx check time (24hr format)"},

    # Sit time
    "sit_time_rolling_avg_days": {"value": "38", "description": "Current rolling average days in queue (seed value)"},

    # Blocked weeks (JSON array of date strings)
    "blocked_weeks": {"value": "[]", "description": "Weeks blocked from scheduling (JSON array of start dates)"},

    # JN sync interval
    "jn_sync_interval_minutes": {"value": "15", "description": "JobNimbus polling interval in minutes"},

    # Note templates (editable via settings UI, version-tracked on each note)
    "note_template_scheduling": {
        "value": "[SCHEDULER SYSTEM -- {timestamp}] Job selected for scheduling on {date_scheduled}. Scoring factors: {days_in_queue} days in queue, {payment_type} payment type, {trade_desc} trade {primary_trade}, {material_type} material. Must-Build anchor: {must_build}. {pm_line}Duration: {duration}. Note generated automatically by Indy Roof Scheduling System.",
        "description": "Template for scheduling decision notes",
    },
    "note_template_not_built": {
        "value": "[SCHEDULER SYSTEM -- {timestamp}] Job returned to scheduling queue. Reason: {reason}. {detail_line}Rescheduled count: {rescheduled_count}. Note generated automatically by Indy Roof Scheduling System.",
        "description": "Template for not-built notes",
    },
    "note_template_secondary_trade_alert": {
        "value": "[SCHEDULER SYSTEM -- {timestamp}] Primary trade ({primary_trade}) completed. Secondary trades remaining: {remaining_trades}. Days since primary completion: {days_since_primary}. Note generated automatically by Indy Roof Scheduling System.",
        "description": "Template for secondary trade alert notes",
    },
    "note_template_weather_rollback": {
        "value": "[SCHEDULER SYSTEM -- {timestamp}] Scheduled build removed due to weather conditions. Forecast detail: {weather_detail}. Job returned to scheduling queue with elevated priority. Note generated automatically by Indy Roof Scheduling System.",
        "description": "Template for weather rollback notes",
    },
    "note_template_standalone_rule": {
        "value": "[SCHEDULER SYSTEM -- {timestamp}] Standalone Rule triggered. No viable cluster partners within 40 miles. Option selected: {option_desc}. Payment type: {payment_type}. Days in queue: {days_in_queue}. Note generated automatically by Indy Roof Scheduling System.",
        "description": "Template for standalone rule notes",
    },
}


def seed_defaults(db):
    """Seed default settings into the database."""
    for key, data in DEFAULT_SETTINGS.items():
        existing = db.query(SystemSettings).filter(SystemSettings.key == key).first()
        if not existing:
            db.add(SystemSettings(key=key, value=data["value"], description=data.get("description", "")))
    db.commit()
