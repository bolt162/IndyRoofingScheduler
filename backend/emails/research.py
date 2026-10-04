"""
Research shingle products that aren't in the built-in table (products.py).

Rule (from Aaron): never guess an impact rating or composition. When a new product shows
up on a material order, look it up from manufacturer sources, record impact class
(Class 4 / Class 3 / none) and composition (oxidized vs polymer modified) with sources,
Thoroughly researched results are approved automatically (Aaron, 2026-10-03); anything
less waits for office approval. Until a row is approved, emails use the no-rating Week 2
version. The office is emailed the findings either way and can correct them.

Two steps:
  1. research with web search (manufacturer spec sheets first), free text with sources
  2. extract the findings into a fixed JSON shape (structured output, no tools)
"""
import json
import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

from backend.emails.products import (
    OXIDIZED, POLYMER_MODIFIED, ProductInfo, from_approved, lookup_shingle, product_key,
)
from backend.models.email import ProductClassification

logger = logging.getLogger("emails.research")

RESEARCH_MODEL = os.getenv("ANTHROPIC_RESEARCH_MODEL", "claude-opus-5-5")
MAX_ATTEMPTS = 3
MAX_PAUSE_CONTINUATIONS = 5

WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

RESEARCH_PROMPT = """You are classifying a roofing shingle for a roofing contractor's customer emails.
The product name below comes from a supplier material order.

Product: {product}

Find, from the manufacturer's own spec sheet or product page wherever possible:
1. The manufacturer and the product line name (for example "GAF Timberline HDZ").
2. The impact resistance rating under UL 2218 or FM 4473: Class 4, Class 3, or no impact rating.
   Some lines have a separate impact-resistant version (for example an "IR" or "AS" variant);
   say which version this order is for, and if it's ambiguous, say so.
3. The asphalt composition: oxidized (traditional) asphalt or polymer modified (SBS, rubberized,
   NEX, and similar). Impact class and composition are independent: a Class 3 shingle can be
   oxidized, and a polymer modified shingle can lack a rating.

Do not guess. If a source doesn't state something, say it's unknown. List every source URL you used."""

EXTRACT_PROMPT = """Extract the findings below into the JSON schema. Use "unknown" whenever the research
does not clearly establish a value. Only use URLs that appear in the research.

Product as ordered: {product}

Research:
{notes}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "manufacturer": {"type": "string"},
        "product_line": {"type": "string"},
        "impact_class": {"type": "string", "enum": ["class_4", "class_3", "none", "unknown"]},
        "composition": {"type": "string", "enum": ["oxidized", "polymer_modified", "unknown"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "summary": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"url": {"type": "string"}, "title": {"type": "string"}},
                "required": ["url", "title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["manufacturer", "product_line", "impact_class", "composition",
                 "confidence", "summary", "sources"],
    "additionalProperties": False,
}

IMPACT = {"class_4": 4, "class_3": 3, "none": None}

# Manufacturer websites. A thorough result must cite at least one of these.
MANUFACTURER_DOMAINS = {
    "gaf": ["gaf.com"],
    "iko": ["iko.com"],
    "owens corning": ["owenscorning.com"],
    "malarkey": ["malarkeyroofing.com"],
    "certainteed": ["certainteed.com"],
    "tamko": ["tamko.com"],
    "atlas": ["atlasroofing.com"],
    "davinci": ["davinciroofscapes.com"],
    "decra": ["decra.com"],
}
AUTO_REVIEWER = "auto-approved (thorough research)"
COMPOSITION = {"oxidized": OXIDIZED, "polymer_modified": POLYMER_MODIFIED}


class ResearchError(Exception):
    pass


def _client():
    import anthropic
    from backend.config import settings
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text").strip()


def research_product(product_text: str, client=None) -> dict:
    """Research one product. Returns the extracted dict (SCHEMA). Raises ResearchError."""
    client = client or _client()
    prompt = RESEARCH_PROMPT.format(product=product_text)
    messages = [{"role": "user", "content": prompt}]

    response = None
    for _ in range(MAX_PAUSE_CONTINUATIONS):
        response = client.beta.messages.create(
            model=RESEARCH_MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            tools=WEB_TOOLS,
            messages=messages,
        )
        if response.stop_reason != "pause_turn":
            break
        # A long server-side tool turn paused; send it back to continue
        messages = [{"role": "user", "content": prompt},
                    {"role": "assistant", "content": response.content}]
    if response is None or response.stop_reason == "refusal":
        raise ResearchError("research request was declined")
    if response.stop_reason == "pause_turn":
        raise ResearchError("research did not finish")
    notes = _text(response)
    if not notes:
        raise ResearchError("research returned no text")

    extracted = client.messages.create(
        model=RESEARCH_MODEL,
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": EXTRACT_PROMPT.format(product=product_text, notes=notes)}],
    )
    if extracted.stop_reason == "refusal":
        raise ResearchError("extraction was declined")
    try:
        return json.loads(_text(extracted))
    except json.JSONDecodeError as e:
        raise ResearchError(f"extraction was not valid JSON: {e}")


def _host(url: str) -> str:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def cites_manufacturer(manufacturer: str | None, sources: list[dict]) -> bool:
    """True if any source is on the manufacturer's own website."""
    mfr = (manufacturer or "").lower().strip()
    domains = next((d for k, d in MANUFACTURER_DOMAINS.items() if k in mfr), None)
    for src in sources or []:
        host = _host(src.get("url", ""))
        if not host:
            continue
        if domains is not None:
            if any(host == d or host.endswith("." + d) for d in domains):
                return True
        elif mfr and host.split(".")[-2:-1] and host.split(".")[-2].startswith(mfr.replace(" ", "")):
            # Unlisted brand: accept its own domain, e.g. "Pabco" -> pabcoroofing.com
            return True
    return False


def is_thorough(data: dict) -> bool:
    """Confirmed class and composition, high confidence, and a manufacturer source."""
    return (
        data.get("impact_class") in IMPACT
        and data.get("composition") in COMPOSITION
        and data.get("confidence") == "high"
        and cites_manufacturer(data.get("manufacturer"), data.get("sources") or [])
    )


def apply_research(row: ProductClassification, data: dict) -> None:
    """Store research results on the row and move it to pending_review."""
    mfr = (data.get("manufacturer") or "").strip()
    line = (data.get("product_line") or "").strip()
    row.manufacturer = mfr if mfr.lower() != "unknown" else None
    if line and line.lower() != "unknown":
        row.display_name = line if not mfr or line.lower().startswith(mfr.lower()) else f"{mfr} {line}"
    row.impact_class = IMPACT.get(data.get("impact_class"))
    row.composition = COMPOSITION.get(data.get("composition"))
    row.confidence = data.get("confidence")
    unknown = [f for f in ("impact_class", "composition") if data.get(f) == "unknown"]
    note = f" Could not confirm: {', '.join(unknown)}." if unknown else ""
    row.summary = (data.get("summary") or "").strip() + note
    row.sources = json.dumps(data.get("sources") or [])
    row.last_error = None
    if is_thorough(data):
        row.status = "approved"
        row.reviewed_by = AUTO_REVIEWER
        row.reviewed_at = datetime.utcnow()
    else:
        row.status = "pending_review"


# ---------------------------------------------------------------------------
# Database helpers used by the email runner
# ---------------------------------------------------------------------------

def resolve_product(db: Session, raw_text: str, job_id: int | None = None) -> tuple[ProductInfo | None, bool]:
    """
    Return (product, office_flag) for a shingle line from a material order.
      built-in table hit      -> (info, False)
      approved researched row -> (info, False)
      anything else           -> (None, True); a research row is created if new
    """
    if not raw_text:
        return None, False
    info = lookup_shingle(raw_text)
    if info:
        return info, False
    key = product_key(raw_text)
    if not key:
        return None, False
    row = db.query(ProductClassification).filter(ProductClassification.product_key == key).first()
    if row and row.status == "approved":
        return from_approved(row), False
    if row is None:
        db.add(ProductClassification(product_key=key, raw_text=raw_text[:2000], status="new",
                                     research_attempts=0, first_job_id=job_id))
        db.commit()
    return None, True


def run_pending_research(db: Session, client=None, limit: int = 10) -> list[ProductClassification]:
    """Research new (and previously failed) products. Returns the rows researched this run
    (auto-approved or awaiting review) so the office can be told about each."""
    rows = (
        db.query(ProductClassification)
        .filter(ProductClassification.status.in_(["new", "research_failed"]),
                ProductClassification.research_attempts < MAX_ATTEMPTS)
        .order_by(ProductClassification.created_at)
        .limit(limit)
        .all()
    )
    ready = []
    for row in rows:
        row.research_attempts = (row.research_attempts or 0) + 1
        try:
            apply_research(row, research_product(row.raw_text, client=client))
            ready.append(row)
        except Exception as e:
            logger.warning(f"Product research failed for '{row.raw_text[:80]}': {e}")
            row.status = "research_failed"
            row.last_error = str(e)[:1000]
        db.commit()
    return ready


def review(db: Session, row_id: int, approve: bool, reviewer: str,
           impact_class: int | None = ..., composition: str | None = ...) -> ProductClassification:
    """Office approves (optionally correcting the class/composition) or rejects a researched product."""
    row = db.query(ProductClassification).filter(ProductClassification.id == row_id).first()
    if row is None:
        raise ValueError("product not found")
    if impact_class is not ...:
        if impact_class not in (None, 3, 4):
            raise ValueError("impact_class must be 3, 4, or None")
        row.impact_class = impact_class
    if composition is not ...:
        if composition not in (None, OXIDIZED, POLYMER_MODIFIED):
            raise ValueError("invalid composition")
        row.composition = composition
    row.status = "approved" if approve else "rejected"
    row.reviewed_by = reviewer
    row.reviewed_at = datetime.utcnow()
    db.commit()
    return row


def review_summary(row: ProductClassification) -> str:
    """Plain text for the office alert email."""
    cls = {4: "Class 4", 3: "Class 3"}.get(row.impact_class, "No impact rating")
    comp = {OXIDIZED: "oxidized asphalt", POLYMER_MODIFIED: "polymer modified"}.get(row.composition, "composition unknown")
    srcs = json.loads(row.sources or "[]")
    name = row.display_name or row.raw_text
    if row.status == "approved":
        head = (f"New shingle product researched and approved automatically: {name}. "
                "If anything below is wrong, correct it on the Settings page.")
        tail = "Customers with this product now get the matching insurance tip."
    else:
        head = (f"New shingle product researched and waiting for approval: {name}. "
                "The research couldn't confirm everything, so please review it on the Settings page.")
        tail = "Until it's approved, customers get the insurance tip without an impact rating."
    lines = [
        head,
        f"As ordered: {row.raw_text}",
        f"Finding: {cls}, {comp} (confidence: {row.confidence or 'unknown'})",
        row.summary or "",
        "Sources: " + ("; ".join(s.get("url", "") for s in srcs) or "none"),
        tail,
    ]
    return "\n\n".join(l for l in lines if l)
