"""
JobNimbus API Client — READ-ONLY.
No data is ever written to JobNimbus through this service.
Notes are generated locally and displayed in the UI only.
"""
import httpx
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job, JobBucket, LOW_SLOPE_MATERIALS, SPECIALTY_MATERIALS, MaterialType


HEADERS = {
    "Authorization": f"Bearer {settings.JOBNIMBUS_API_KEY}",
    "Content-Type": "application/json",
}

BASE_URL = settings.JOBNIMBUS_BASE_URL


def _jn_get(endpoint: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    resp = httpx.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_jobs_at_status(status_label: str = "Schedule Job") -> list[dict]:
    """Fetch all active jobs from JN and filter by status_name."""
    data = _jn_get("jobs", params={"must": "active", "count": 5000})
    results = data.get("results", []) if isinstance(data, dict) else data
    return [j for j in results if j.get("status_name") == status_label]


def fetch_job_by_id(jn_job_id: str) -> dict:
    """Fetch a single job from JN by its ID."""
    return _jn_get(f"jobs/{jn_job_id}")


def fetch_contacts_for_job(jn_job_id: str) -> list[dict]:
    """Fetch contacts linked to a JN job."""
    data = _jn_get(f"jobs/{jn_job_id}/contacts")
    return data.get("results", data) if isinstance(data, dict) else data


def fetch_notes_for_job(jn_job_id: str) -> list[dict]:
    """Fetch all activity/notes for a JN job."""
    data = _jn_get(f"activities", params={"job_id": jn_job_id})
    return data.get("results", data) if isinstance(data, dict) else data


def _classify_duration_tier(material_type: str | None, square_footage: float | None) -> tuple[str, bool, bool]:
    """Returns (tier, duration_confirmed, crew_requirement_flag)."""
    mat = material_type.lower() if material_type else ""

    # Low slope materials -> hard gate
    if mat in {m.value for m in LOW_SLOPE_MATERIALS}:
        return "low_slope", False, False

    # Specialty materials -> tier 3 + crew requirement
    if mat in {m.value for m in SPECIALTY_MATERIALS}:
        return "tier_3", False, True

    # Siding
    if mat == "siding":
        return "tier_2", False, False

    # Residential shingles by square footage
    if square_footage is not None:
        if square_footage <= 30:
            return "tier_1", True, False
        elif square_footage <= 60:
            return "tier_2", False, False
        else:
            return "tier_3", False, False

    return "tier_2", False, False


def map_jn_job_to_model(jn_data: dict) -> dict:
    """
    Map JN API response fields to our Job model fields.
    Field mappings validated against actual JN API response (March 2026).
    """
    # Address: address_line1, address_line2, city, state_text, zip
    address_parts = []
    for f in ["address_line1", "address_line2", "city", "state_text", "zip"]:
        val = jn_data.get(f, "")
        if val:
            address_parts.append(str(val))
    address = ", ".join(address_parts)

    # Lat/lng from geo object (JN provides these directly)
    geo = jn_data.get("geo") or {}
    latitude = geo.get("lat")
    longitude = geo.get("lon")  # JN uses "lon" not "lng"

    # Material type from "Roof Material Type" custom field (e.g. "IKO", "OC")
    # or fall back to "Trade #1" for siding detection
    material_type = (jn_data.get("Roof Material Type") or "").lower()
    trade_1 = (jn_data.get("Trade #1") or jn_data.get("cf_string_11") or "").lower()
    if not material_type and trade_1 == "siding":
        material_type = "siding"

    # Square footage from "Roof Total Square" custom field
    square_footage = jn_data.get("Roof Total Square")
    if square_footage:
        try:
            square_footage = float(square_footage)
        except (ValueError, TypeError):
            square_footage = None

    tier, dur_confirmed, crew_flag = _classify_duration_tier(material_type, square_footage)

    # Parse date_created (unix timestamp)
    date_entered = None
    raw_date = jn_data.get("date_created")
    if raw_date:
        if isinstance(raw_date, (int, float)) and raw_date > 0:
            date_entered = datetime.fromtimestamp(raw_date)
        elif isinstance(raw_date, str):
            try:
                date_entered = datetime.fromisoformat(raw_date)
            except ValueError:
                pass

    # Job type from record_type_name (e.g. "Insurance", "Retail")
    job_type = (jn_data.get("record_type_name") or "").lower()

    # Payment type derived from job_type
    payment_type = "insurance" if job_type == "insurance" else "cash"

    # Primary trade from "Trade #1" custom field
    primary_trade = trade_1 or "roofing"

    # Customer name from "name" field (format: "customer name - J-XXXXX")
    raw_name = jn_data.get("name") or ""
    # Extract customer name (strip job number suffix)
    customer_name = raw_name.split(" - ")[0].strip() if " - " in raw_name else raw_name

    # Sales rep
    sales_rep = jn_data.get("sales_rep_name") or ""

    # Description (useful for AI note scanning)
    description = jn_data.get("description") or ""

    return {
        "jn_job_id": str(jn_data.get("jnid") or ""),
        "customer_name": customer_name,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "job_type": job_type,
        "payment_type": payment_type,
        "primary_trade": primary_trade,
        "secondary_trades": [],
        "material_type": material_type,
        "square_footage": square_footage,
        "date_entered": date_entered,
        "sales_rep": sales_rep,
        "duration_days": 1,
        "duration_confirmed": dur_confirmed,
        "duration_tier": tier,
        "crew_requirement_flag": crew_flag,
        "jn_status": jn_data.get("status_name") or "",
        "bucket": JobBucket.TO_SCHEDULE.value,
        "jn_notes_raw": description,
    }


def sync_jobs_from_jn(db: Session) -> dict:
    """
    Sync jobs from JN into our database. READ-ONLY — only creates/updates local records.
    Returns sync summary.
    """
    jn_jobs = fetch_jobs_at_status("Schedule Job")
    created = 0
    updated = 0
    errors = []

    for jn_data in jn_jobs:
        try:
            mapped = map_jn_job_to_model(jn_data)
            jn_id = mapped["jn_job_id"]

            existing = db.query(Job).filter(Job.jn_job_id == jn_id).first()
            if existing:
                # Update fields that may have changed
                for field in ["customer_name", "address", "latitude", "longitude",
                              "payment_type", "material_type", "square_footage",
                              "sales_rep", "jn_status"]:
                    if mapped.get(field):
                        setattr(existing, field, mapped[field])
                existing.last_synced_at = datetime.utcnow()
                updated += 1
            else:
                # Fetch notes for new jobs
                try:
                    notes = fetch_notes_for_job(jn_id)
                    notes_text = "\n---\n".join(
                        f"[{n.get('date_created', 'unknown date')}] {n.get('note', n.get('description', ''))}"
                        for n in notes if isinstance(n, dict)
                    )
                    mapped["jn_notes_raw"] = notes_text
                except Exception:
                    mapped["jn_notes_raw"] = ""

                job = Job(**mapped)
                job.last_synced_at = datetime.utcnow()
                db.add(job)
                created += 1

        except Exception as e:
            errors.append({"jn_id": jn_data.get("jnid", "unknown"), "error": str(e)})

    db.commit()
    return {
        "synced_at": datetime.utcnow().isoformat(),
        "created": created,
        "updated": updated,
        "errors": errors,
        "total_from_jn": len(jn_jobs),
    }
