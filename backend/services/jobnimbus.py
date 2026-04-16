"""
JobNimbus API Client.
Primarily READ-ONLY — fetches jobs and notes from JN.
The ONLY write operation is push_note_to_jn() which creates a note activity
on a JN job. This is triggered manually by the scheduler (never automatic).
"""
import httpx
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job, JobBucket, LOW_SLOPE_MATERIALS, SPECIALTY_MATERIALS, MaterialType, TradeType


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


def _jn_post(endpoint: str, body: dict) -> dict:
    """POST to a JN endpoint. Used only for pushing notes (activities)."""
    url = f"{BASE_URL}/{endpoint}"
    resp = httpx.post(url, headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def push_note_to_jn(jn_job_id: str, note_text: str) -> dict:
    """
    Create a note activity on a JN job.
    Returns the created activity dict with the new 'jnid'.
    Raises httpx.HTTPError on failure.
    """
    body = {
        "parent": jn_job_id,           # JN link to job
        "type": "note",
        "record_type_name": "Note",
        "note": note_text,
    }
    return _jn_post("activities", body)


def fetch_jobs_at_status(status_label: str = "Schedule Job") -> list[dict]:
    """Fetch all active jobs from JN and filter by status_name."""
    data = _jn_get("jobs", params={"must": "active", "count": 5000})
    results = data.get("results", []) if isinstance(data, dict) else data
    return [j for j in results if j.get("status_name") == status_label]


def fetch_jobs_at_tracked_statuses() -> list[dict]:
    """Fetch all active jobs whose JN status maps to a scheduler bucket."""
    data = _jn_get("jobs", params={"must": "active", "count": 5000})
    results = data.get("results", []) if isinstance(data, dict) else data
    return [j for j in results if j.get("status_name") in TRACKED_JN_STATUSES]


def fetch_job_by_id(jn_job_id: str) -> dict:
    """Fetch a single job from JN by its ID."""
    return _jn_get(f"jobs/{jn_job_id}")


def fetch_contacts_for_job(jn_job_id: str) -> list[dict]:
    """Fetch contacts linked to a JN job."""
    data = _jn_get(f"jobs/{jn_job_id}/contacts")
    return data.get("results", data) if isinstance(data, dict) else data


def fetch_notes_for_job(jn_job_id: str) -> list[dict]:
    """Fetch all activity/notes for a JN job."""
    # JN API uses parent_jnid to filter activities by parent job
    data = _jn_get("activities", params={"parent_jnid": jn_job_id, "count": 100})
    return data.get("results", data) if isinstance(data, dict) else data


TRADE_ALIASES = {
    "roofing": "roofing", "roof": "roofing",
    "siding": "siding", "side": "siding",
    "gutters": "gutters", "gutter": "gutters",
    "windows": "windows", "window": "windows",
    "paint": "paint", "painting": "paint",
    "interior": "interior",
}
VALID_TRADES = {t.value for t in TradeType}


def _normalize_trade(raw: str) -> str:
    """Normalize a raw JN trade string to a valid TradeType enum value."""
    raw = raw.lower().strip()
    if raw in VALID_TRADES:
        return raw
    return TRADE_ALIASES.get(raw, "other" if raw else "roofing")


MATERIAL_ALIASES = {
    # Manufacturer brands (all produce asphalt shingles)
    "oc": "asphalt", "owens corning": "asphalt",
    "iko": "asphalt", "gaf": "asphalt",
    "certainteed": "asphalt", "atlas": "asphalt",
    "tamko": "asphalt", "malarkey": "asphalt",
    # Direct enum matches
    "asphalt": "asphalt", "shingle": "asphalt", "shingles": "asphalt",
    "polymer_modified": "polymer_modified", "polymer modified": "polymer_modified",
    "modified bitumen": "polymer_modified",
    "tpo": "tpo",
    "duro_last": "duro_last", "duro-last": "duro_last", "durolast": "duro_last",
    "epdm": "epdm",
    "coating": "coating",
    "wood_shake": "wood_shake", "wood shake": "wood_shake",
    "cedar shake": "wood_shake", "shake": "wood_shake",
    "slate": "slate",
    "metal": "metal", "standing seam": "metal", "metal roof": "metal",
    "siding": "siding",
}
VALID_MATERIALS = {m.value for m in MaterialType}

# JN status_name → scheduler bucket mapping
# Only statuses listed here are fetched during sync — everything else is ignored
JN_STATUS_TO_BUCKET = {
    # Pending Confirmation — awaiting manual duration/crew confirmation
    "Permit Required": "pending_confirmation",
    "Not Ready for Scheduling": "pending_confirmation",
    # Coming Soon — approved, materials ordered, not yet schedulable
    "Order/Schedule": "coming_soon",
    "Procurement": "coming_soon",
    "Pending Start Date": "coming_soon",
    "Pending Materials": "coming_soon",
    "Permit & Order": "coming_soon",
    # To Schedule — enters scoring engine
    "Schedule Job": "to_schedule",
    "Schedule Production": "to_schedule",
    # Scheduled — plan confirmed, actively being built
    "Job In Progress": "scheduled",
    "In Production": "scheduled",
    # Primary Complete — primary trade done, secondaries open
    "Other Trades": "primary_complete",
    # Review for Completion
    "COC / Punch List": "review_for_completion",
    # Completed
    "Job Complete (Job Review)": "completed",
    "Completed": "completed",
}
TRACKED_JN_STATUSES = set(JN_STATUS_TO_BUCKET.keys())


def _normalize_material(raw: str) -> str:
    """Normalize a raw JN material string to a valid MaterialType enum value."""
    raw = raw.lower().strip()
    if not raw:
        return ""
    if raw in VALID_MATERIALS:
        return raw
    if raw in MATERIAL_ALIASES:
        return MATERIAL_ALIASES[raw]
    # Fuzzy: check if any alias key is contained in the raw value
    for alias, normalized in MATERIAL_ALIASES.items():
        if alias in raw:
            return normalized
    return "other"


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

    # Residential shingles by square footage (in sq ft, converted from squares)
    if square_footage is not None:
        if square_footage <= 3000:      # ≤30 squares
            return "tier_1", True, False
        elif square_footage <= 6000:    # 31-60 squares
            return "tier_2", False, False
        else:                           # 61+ squares
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

    # Material type from "Roof Material Type" custom field, normalized to MaterialType enum.
    # NOTE: Siding is a TRADE not a material — never put "siding" in material_type.
    # Siding-specific weather thresholds are applied via primary_trade in weather.py.
    raw_material = (jn_data.get("Roof Material Type") or "").lower()
    material_type = _normalize_material(raw_material)

    # Square footage from "Roof Total Square" custom field
    # JN stores this in "squares" (1 square = 100 sq ft), so multiply by 100
    raw_squares = jn_data.get("Roof Total Square")
    square_footage = None
    if raw_squares:
        try:
            square_footage = float(raw_squares) * 100  # Convert squares to sq ft
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
    raw_job_type = (jn_data.get("record_type_name") or "").lower()
    job_type = "insurance" if raw_job_type == "insurance" else "retail"

    # Payment type from JN custom field, fallback to job_type derivation
    raw_payment = (jn_data.get("Payment Type") or jn_data.get("cf_payment_type") or "").lower()
    if raw_payment in ("cash", "finance", "insurance"):
        payment_type = raw_payment
    elif "financ" in raw_payment:
        payment_type = "finance"
    elif "insur" in raw_payment:
        payment_type = "insurance"
    else:
        payment_type = "insurance" if job_type == "insurance" else "cash"

    # Primary trade from "Trade #1" custom field, normalized to TradeType enum
    primary_trade = _normalize_trade(trade_1)

    # Secondary trades from "Trade #2" and "Trade #3" custom fields
    raw_trade_2 = (jn_data.get("Trade #2") or jn_data.get("cf_string_12") or "").lower()
    raw_trade_3 = (jn_data.get("Trade #3") or jn_data.get("cf_string_13") or "").lower()
    secondary_trades = []
    for raw in [raw_trade_2, raw_trade_3]:
        if raw:
            normalized = _normalize_trade(raw)
            if normalized != primary_trade and normalized not in secondary_trades:
                secondary_trades.append(normalized)

    # Customer name from "name" field (format: "customer name - J-XXXXX")
    raw_name = jn_data.get("name") or ""
    # Extract customer name (strip job number suffix)
    customer_name = raw_name.split(" - ")[0].strip() if " - " in raw_name else raw_name

    # Sales rep
    sales_rep = jn_data.get("sales_rep_name") or ""

    # Description (useful for AI note scanning)
    description = jn_data.get("description") or ""

    # Bucket assignment: derive from JN status, with auto-transitions
    jn_status = jn_data.get("status_name") or ""
    bucket = JN_STATUS_TO_BUCKET.get(jn_status, JobBucket.TO_SCHEDULE.value)

    # Low-slope hard gate: override to pending_confirmation (spec §4.2)
    if tier == "low_slope" and not dur_confirmed:
        bucket = "pending_confirmation"

    # Auto-transition: Primary Complete with open secondaries → Waiting on Trades (spec §8.2)
    if bucket == "primary_complete" and secondary_trades:
        bucket = "waiting_on_trades"

    return {
        "jn_job_id": str(jn_data.get("jnid") or ""),
        "customer_name": customer_name,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "job_type": job_type,
        "payment_type": payment_type,
        "primary_trade": primary_trade,
        "secondary_trades": secondary_trades,
        "material_type": material_type,
        "square_footage": square_footage,
        "date_entered": date_entered,
        "sales_rep": sales_rep,
        "duration_days": 1,
        "duration_confirmed": dur_confirmed,
        "duration_tier": tier,
        "crew_requirement_flag": crew_flag,
        "jn_status": jn_status,
        "bucket": bucket,
        "jn_notes_raw": description,
    }


def sync_jobs_from_jn(db: Session) -> dict:
    """
    Sync jobs from JN into our database. READ-ONLY — only creates/updates local records.
    Returns sync summary.
    """
    jn_jobs = fetch_jobs_at_tracked_statuses()
    created = 0
    updated = 0
    errors = []

    for jn_data in jn_jobs:
        try:
            mapped = map_jn_job_to_model(jn_data)
            jn_id = mapped["jn_job_id"]

            # Build jn_notes_raw: job description + any JN activities/notes
            notes_parts = []
            description = jn_data.get("description") or ""
            if description.strip():
                notes_parts.append(f"[Job Description] {description}")
            try:
                activities = fetch_notes_for_job(jn_id)
                for n in activities:
                    if isinstance(n, dict):
                        note_text = n.get("note") or n.get("description") or ""
                        if note_text.strip():
                            notes_parts.append(f"[Note] {note_text}")
            except Exception:
                pass
            jn_notes_raw = "\n---\n".join(notes_parts)

            existing = db.query(Job).filter(Job.jn_job_id == jn_id).first()
            if existing:
                # Update fields that may have changed
                for field in ["customer_name", "address", "latitude", "longitude",
                              "payment_type", "material_type", "square_footage",
                              "sales_rep", "jn_status", "bucket", "duration_tier",
                              "duration_confirmed", "crew_requirement_flag"]:
                    if mapped.get(field) is not None:
                        setattr(existing, field, mapped[field])
                # Update notes only if they actually changed (avoids unnecessary re-scans)
                if jn_notes_raw and jn_notes_raw != (existing.jn_notes_raw or ""):
                    existing.jn_notes_raw = jn_notes_raw
                existing.last_synced_at = datetime.utcnow()
                updated += 1
            else:
                mapped["jn_notes_raw"] = jn_notes_raw
                job = Job(**mapped)
                job.last_synced_at = datetime.utcnow()
                db.add(job)
                created += 1

        except Exception as e:
            errors.append({"jn_id": jn_data.get("jnid", "unknown"), "error": str(e)})

    db.commit()

    # Scan AI notes for NEW jobs only (never-scanned jobs where ai_note_scan_result is NULL)
    # This runs after sync so only newly created jobs get scanned — existing jobs are skipped
    scanned = 0
    if created > 0:
        try:
            from backend.services.note_scanner import scan_all_unscanned_jobs
            scan_result = scan_all_unscanned_jobs(db)
            scanned = scan_result.get("scanned", 0)
        except Exception:
            pass  # Don't fail the sync if scanning fails

    return {
        "synced_at": datetime.utcnow().isoformat(),
        "created": created,
        "updated": updated,
        "scanned": scanned,
        "errors": errors,
        "total_from_jn": len(jn_jobs),
    }
