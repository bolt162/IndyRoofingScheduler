"""
Shingle product lookup. Impact ratings come ONLY from this table (plus office-approved
research results), never typed into an email by hand. Anything not on the list gets
Week 2 Version C and an office flag, and is sent for research (see research.py).

Impact class and composition are independent: OC Duration is Class 3 but oxidized
asphalt; Malarkey Highlander is Class 3 and polymer modified. GAF and IKO each sell
both kinds, so classify by product line, never by brand.
"""
import re
from dataclasses import dataclass

OXIDIZED = "oxidized"
POLYMER_MODIFIED = "polymer_modified"


@dataclass(frozen=True)
class ProductInfo:
    display_name: str       # used for {shingle_line}
    manufacturer: str       # "Owens Corning" / "Malarkey"
    impact_class: int | None
    composition: str | None  # OXIDIZED / POLYMER_MODIFIED / None if not confirmed

    @property
    def week2_version(self) -> str:
        """A = Class 4, B = Class 3, C = no rating."""
        return {4: "A", 3: "B"}.get(self.impact_class, "C")


# Confirmed by Aaron. Order matters: more specific names first ("duration flex" before
# "duration"). Keys are matched against the product text from JobNimbus material orders.
_PRODUCTS: list[tuple[str, ProductInfo]] = [
    ("vista", ProductInfo("Malarkey Vista", "Malarkey", 4, None)),
    ("windsor", ProductInfo("Malarkey Windsor", "Malarkey", 4, None)),
    ("legacy", ProductInfo("Malarkey Legacy", "Malarkey", 4, None)),
    ("highlander", ProductInfo("Malarkey Highlander", "Malarkey", 3, POLYMER_MODIFIED)),
    ("duration flex", ProductInfo("Owens Corning Duration FLEX", "Owens Corning", 4, None)),
    ("duration", ProductInfo("Owens Corning Duration", "Owens Corning", 3, OXIDIZED)),
    ("oakridge", ProductInfo("Owens Corning Oakridge", "Owens Corning", None, OXIDIZED)),
]

_MANUFACTURERS = {
    "owens corning": "Owens Corning",
    "malarkey": "Malarkey",
    "certainteed": "CertainTeed",
    "james hardie": "James Hardie",
    "hardie": "James Hardie",
    "wilco": "Wilco",
}

CREDENTIAL_LINES = {
    "Owens Corning": (
        "We're an Owens Corning Preferred Contractor, a status Owens Corning gives only to "
        "contractors who meet its standards, and we work any warranty question directly with "
        "our Owens Corning rep."
    ),
    "Malarkey": (
        "We're a certified Malarkey contractor, and we work any warranty question directly "
        "with Malarkey for you."
    ),
}


def lookup_shingle(raw: str | None) -> ProductInfo | None:
    """Return product info for a known shingle line, or None if unknown/blank."""
    if not raw:
        return None
    text = " ".join(raw.lower().replace("-", " ").split())
    for key, info in _PRODUCTS:
        if key in text:
            return info
    return None


def product_key(raw: str | None) -> str:
    """
    Stable key for a material order product line, used to match researched products.
    Drops the color/variant in parentheses and pack sizes so every color of one line
    maps to the same key.
    """
    if not raw:
        return ""
    text = raw.split("(")[0].lower()
    text = re.sub(r"\d+\s*bundles?\s*per\s*square", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())[:300]


def from_approved(row) -> ProductInfo:
    """Turn an office-approved ProductClassification row into a ProductInfo."""
    return ProductInfo(
        display_name=row.display_name or row.raw_text,
        manufacturer=row.manufacturer or "",
        impact_class=row.impact_class if row.impact_class in (3, 4) else None,
        composition=row.composition,
    )


def manufacturer_from_text(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.lower()
    for key, name in _MANUFACTURERS.items():
        if key in text:
            return name
    return None


def credential_line(manufacturer: str | None) -> str:
    return CREDENTIAL_LINES.get(manufacturer or "", "")
