"""
Fill JobNimbus's "Roof Material Type" from the job's material order when nobody has (Aaron 2026-10-27).

Winter builds hang on it: polymer modified shingles go on down to 20°F, oxidized asphalt needs 40°F
(weather_*_min_temp settings). The order names the exact shingle line, and emails/products.py knows
each one (researching any new one). Only a blank box, or an old brand-only answer like "OC", is filled;
a material a person picked is never changed. Runs after each sync; the sync itself stays read-only.
"""
import logging

from sqlalchemy.orm import Session

from backend.emails.jn_data import fetch_material_items, parse_materials
from backend.emails.products import POLYMER_MODIFIED
from backend.emails.research import resolve_product
from backend.services.jobnimbus import _classify_duration_tier, _jn_put, _normalize_material, jn_material_text

logger = logging.getLogger("material_fill")

FIELD = "cf_string_9"  # "Roof Material Type"
JN_WORDS = {"polymer_modified": "Polymer Modified", "asphalt": "Asphalt"}
# Waiting for a build or booked; jobs further along don't need it
BUCKETS = {"pending_confirmation", "coming_soon", "to_schedule", "scheduled", "not_built"}


def from_order(db: Session, job) -> str | None:
    """'polymer_modified' or 'asphalt' from the job's material order, or None when it can't tell yet."""
    m = parse_materials(fetch_material_items(job.jn_job_id))
    if m.is_low_slope or not m.shingle_line:
        return None
    info, _ = resolve_product(db, m.shingle_line, job.id)
    if not info or not info.composition:
        return None
    return "polymer_modified" if info.composition == POLYMER_MODIFIED else "asphalt"


def fill(db: Session, observed: list) -> int:
    """observed: (job, bucket before, raw JobNimbus job) from the sync. Returns how many jobs it filled."""
    filled = 0
    for job, _, jn_data in observed:
        if job.bucket not in BUCKETS or (job.primary_trade or "roofing") != "roofing":
            continue
        if _normalize_material(jn_material_text(jn_data)):  # someone picked it
            continue
        try:
            material = from_order(db, job)
            if not material:
                continue
            _jn_put(f"jobs/{job.jn_job_id}", {FIELD: JN_WORDS[material]})
        except Exception:
            logger.exception("material fill failed for %s", job.jn_number)
            continue
        job.material_type = material
        job.duration_tier, confirmed, job.crew_requirement_flag = _classify_duration_tier(material, job.square_footage)
        if not (job.duration_source or "").startswith("Set by "):
            job.duration_confirmed = confirmed
        filled += 1
    if filled:
        db.commit()
    return filled
