"""
Everything the emails need from JobNimbus that the scheduler doesn't already store.

Read-only. Verified against live JobNimbus data (2026-10-03):
  - customer first name / email / phone: the job's primary contact
  - commercial: the job's record type is "Commercial"
  - shingle product + color, siding product + color: the job's material orders
    (the custom fields for these are blank on every job)
  - JobNimbus's own "Project Update" scheduling email: an Automation activity

Any lookup that fails returns blanks, and the email falls back to generic wording.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from backend.services.jobnimbus import _jn_get

logger = logging.getLogger("emails.jn_data")

JN_JOB_URL = "https://app.jobnimbus.com/job/{jnid}"


@dataclass
class Materials:
    shingle_line: str = ""      # product name as ordered, e.g. "Malarkey Roofing Vista AR 252 ..."
    shingle_color: str = ""
    siding_product: str = ""
    siding_color: str = ""
    gutter_color: str = ""
    is_low_slope: bool = False


@dataclass
class JobDetails:
    jnid: str
    record_type: str = ""
    is_commercial: bool | None = None
    start_date: date | None = None
    first_name: str = ""
    # The job's main contact, "First Last". Emails go to this person even when it isn't the
    # customer named on the job (realtors, family members): that's intentional (Aaron, 2026-10-04).
    contact_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    materials: Materials = field(default_factory=Materials)
    job_link: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Material order parsing
# ---------------------------------------------------------------------------

ACCESSORY = re.compile(
    r"starter|hip\s*&?\s*ridge|ridgeflex|proedge|ridge cap|\bnails?\b|underlayment|smart start|"
    r"drip edge|apron|flashing|vent|ice\s*&?\s*water|caulk|sealant|j[\s-]?channel|soffit|corner|"
    r"undersill|trim|fascia|house\s*wrap|wrap", re.I)
SHINGLE = re.compile(r"shingle|vista|windsor|legacy|highlander|oakridge|duration|timberline|dynasty|nordic|cambridge|landmark", re.I)
LOW_SLOPE = re.compile(r"\btpo\b|\bepdm\b|duro[\s-]?last|modified bitumen|\bmod[\s-]?bit\b|membrane|roof coating", re.I)
SIDING = re.compile(r"siding|dutch\s*lap|lap\b|board\s*&?\s*batten|hardie|vinyl\s+lap", re.I)

# Words that are product/pack info, not color, inside a material order's variant text
_NOT_COLOR = re.compile(
    r"(?i)\b(owens\s*corning|oc|malarkey|roofing|products?|trudefinition|duration|flex|oakridge|vista|"
    r"highlander|windsor|legacy|supreme|gaf|timberline|hdz|iko|dynasty|cambridge|nordic|certainteed|"
    r"landmark|norandex|woodsman|select|mainstreet|monogram|james\s*hardie|hardie|algae[\s-]*resistant|ar|"
    r"architectural|shingles?|vinyl|siding|lap|dutch\s*lap|dutchlap|double|triple|single|solid|matte|"
    r"woodgrain|pieces?|bundles?|per|square|squares|sq|box|ctn|carton)\b")
_SIZES = re.compile(r"\b[dD]?\d+(\.\d+)?\s*(\"|in\b|inch|'|ft)?|\bx\b")


def _clean_color(text: str) -> str:
    """'Owens Corning Oakridge Algae Resistant Driftwood 3 Bundle Per Square' -> 'Driftwood'."""
    t = _SIZES.sub(" ", text or "")
    t = _NOT_COLOR.sub(" ", t)
    t = re.sub(r"[^A-Za-z' ]+", " ", t)
    words = [w for w in t.split() if len(w) > 1 or w.lower() == "a"]
    color = " ".join(words).strip().title()
    # Only trust short, plain-word results; anything else falls back to generic wording
    if not color or len(words) > 4 or len(color) > 30:
        return ""
    return color


def _variant(item: dict) -> str:
    """Supplier variant text: the item's color field, or the part in parentheses."""
    if item.get("color"):
        return str(item["color"])
    m = re.search(r"\(([^)]*)\)", " ".join(str(item.get(k) or "") for k in ("name", "description")))
    return m.group(1) if m else ""


def _siding_product(name: str) -> str:
    """'CertainTeed Mainstreet Double 4" x 12' 6" Vinyl Lap Siding' -> 'CertainTeed Mainstreet'."""
    words = []
    for w in (name or "").split("(")[0].split():
        if re.search(r"\d|\"|'", w) or w.lower() in {"double", "triple", "single", "vinyl", "lap", "siding", "dutchlap", "dutch"}:
            break
        words.append(w)
    product = " ".join(words[:4]).strip()
    return product if len(product) >= 4 else ""


def parse_materials(items: list[dict]) -> Materials:
    m = Materials()
    has_shingle = False
    has_membrane = False
    for it in items:
        name = str(it.get("name") or "")
        text = f"{name} {it.get('description') or ''}"
        if LOW_SLOPE.search(text):
            has_membrane = True
        if ACCESSORY.search(name):
            continue
        if not m.shingle_line and SHINGLE.search(text):
            has_shingle = True
            m.shingle_line = name.split("(")[0].strip()
            m.shingle_color = _clean_color(_variant(it))
        elif not m.siding_product and SIDING.search(text):
            m.siding_product = _siding_product(name)
            m.siding_color = _clean_color(_variant(it))
        elif not m.gutter_color and re.search(r"gutter coil|seamless gutter|k[\s-]?style", text, re.I):
            m.gutter_color = _clean_color(_variant(it))
    m.is_low_slope = has_membrane and not has_shingle
    return m


# ---------------------------------------------------------------------------
# JobNimbus lookups
# ---------------------------------------------------------------------------

def _filter_related(jnid: str) -> str:
    return json.dumps({"must": [{"term": {"related.id": jnid}}]})


def fetch_material_items(jnid: str) -> list[dict]:
    data = _jn_get("v2/materialorders", params={"filter": _filter_related(jnid), "size": 50})
    orders = data.get("results", []) if isinstance(data, dict) else []
    # Newest order first: a re-order reflects the final choice
    orders.sort(key=lambda o: o.get("date_created") or 0, reverse=True)
    return [it for o in orders for it in (o.get("items") or []) if isinstance(it, dict)]


def jn_schedule_email_sent(jnid: str, since: datetime | None = None) -> bool:
    """Did JobNimbus's own 'Project Update' scheduling email go out (since `since`)?"""
    data = _jn_get("activities", params={"filter": _filter_related(jnid), "size": 200})
    acts = data.get("activity", []) if isinstance(data, dict) else []
    cutoff = since.timestamp() if since else 0
    for a in acts:
        note = a.get("note") or ""
        if "Project Update from Indy Roof" in note and (a.get("date_created") or 0) >= cutoff - 3600:
            return True
    return False


def _date(ts) -> date | None:
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts).date()
    return None


def fetch_job_details(jnid: str, with_materials: bool = True) -> JobDetails:
    d = JobDetails(jnid=jnid, job_link=JN_JOB_URL.format(jnid=jnid))
    try:
        job = _jn_get(f"jobs/{jnid}")
        d.record_type = (job.get("record_type_name") or "").strip()
        d.is_commercial = d.record_type.lower() == "commercial" if d.record_type else None
        d.start_date = _date(job.get("date_start"))
        contact_id = (job.get("primary") or {}).get("id")
        if contact_id:
            c = _jn_get(f"contacts/{contact_id}")
            d.first_name = (c.get("first_name") or "").strip().title() if (c.get("first_name") or "").isupper() \
                else (c.get("first_name") or "").strip()
            d.contact_name = " ".join(p for p in ((c.get("first_name") or "").strip(),
                                                   (c.get("last_name") or "").strip()) if p)
            d.customer_email = (c.get("email") or "").strip()
            d.customer_phone = (c.get("mobile_phone") or c.get("home_phone") or c.get("work_phone") or "").strip()
    except Exception as e:  # noqa: BLE001
        d.errors.append(f"job/contact: {e}")
    if with_materials:
        try:
            d.materials = parse_materials(fetch_material_items(jnid))
        except Exception as e:  # noqa: BLE001
            d.errors.append(f"material orders: {e}")
    return d
