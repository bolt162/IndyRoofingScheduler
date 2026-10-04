"""
Rep and PM contact info for emails.

JobNimbus gives us only the rep's name (sales_rep_name). Phone and email come from the
team_contacts table, seeded below on first run and editable afterwards. Anyone not in the
table, or marked inactive, is never named in a customer email: the email falls back to
the office number instead.
"""
import re

from sqlalchemy.orm import Session

from backend.models.email import TeamContact

# Seeded once into an empty team_contacts table (Aaron, 2026-10-03).
# (JobNimbus name, name customers see, role, email, phone)
DEFAULT_TEAM = [
    ("AJ Gratz", "AJ Gratz", "rep", "aj.gratz@indyroofandrestoration.com", "(317) 964-1728"),
    ("Bryan Brown", "Bryan Brown", "rep", "bryan.brown@indyroofandrestoration.com", "(317) 767-1723"),
    ("Daniel Ralston", "Daniel Ralston", "rep", "daniel.ralston@indyroofandrestoration.com", "(317) 847-2670"),
    ("James Clinger", "Jimmy Clinger", "rep", "jimmy.clinger@indyroofandrestoration.com", "(463) 867-2451"),
    ("Mark Sopke", "Mark Sopke", "rep", "mark.sopke@indyroofandrestoration.com", "(317) 945-3689"),
    ("Nick Smith", "Nick Smith", "rep", "nick.smith@indyroofandrestoration.com", "(317) 435-7468"),
    ("Paul Sopke", "Paul Sopke", "rep", "paul.sopke@indyroofandrestoration.com", "(317) 752-1773"),
    ("Joe Venn", "Joe Venn", "rep", "joe.venn@indyroofandrestoration.com", "(317) 667-7119"),
    ("Sherilyn Nowak", "Sherilyn Nowak", "rep", "sherilyn.nowak@indyroofandrestoration.com", "(317) 457-9596"),
    ("Luke Vollenweider", "Luke Vollenweider", "rep", "luke.vollenweider@indyroofandrestoration.com", "(816) 853-4550"),
    ("Lavell Chestnut", "Lavell Chestnut", "rep", "lavell.chestnut@indyroofandrestoration.com", "(317) 752-7003"),
    ("Luke Mroz", "Luke Mroz", "pm", "luke.mroz@indyroofandrestoration.com", None),
    # Not customer-facing: they get the full Wednesday preview of Thursday's send
    ("Greg Russell", "Greg Russell", "ops", "greg.russell@indyroofandrestoration.com", None),
    ("Aaron Christy", "Aaron Christy", "owner", "aaron@indyroofandrestoration.com", None),
]

# Who gets the full preview of Thursday's send. Reps get a copy with only their customers.
FULL_PREVIEW_ROLES = ("owner", "ops", "pm")


def _key(name: str | None) -> str:
    return " ".join((name or "").lower().split())


def seed_team(db: Session) -> int:
    """Insert DEFAULT_TEAM if the table is empty. Never overwrites edits. Returns rows added."""
    if db.query(TeamContact).count():
        return 0
    for jn_name, display, role, email, phone in DEFAULT_TEAM:
        db.add(TeamContact(jn_name=jn_name, display_name=display, role=role,
                           email=email, phone=phone, is_active=True))
    db.commit()
    return len(DEFAULT_TEAM)


def rep_contact(db: Session, jn_name: str | None) -> dict:
    """
    Contact info for the rep on a job. Returns blanks unless the rep is an active team
    member, so a former rep's name never reaches a customer.
    """
    blank = {"rep_name": "", "rep_phone": "", "rep_email": ""}
    key = _key(jn_name)
    if not key:
        return blank
    for row in db.query(TeamContact).filter(TeamContact.is_active.is_(True), TeamContact.role == "rep").all():
        if _key(row.jn_name) == key:
            return {"rep_name": row.display_name, "rep_phone": row.phone or "", "rep_email": row.email or ""}
    return blank


def active_pms(db: Session) -> list[TeamContact]:
    return db.query(TeamContact).filter(TeamContact.is_active.is_(True), TeamContact.role == "pm").all()


def full_preview_recipients(db: Session) -> list[str]:
    rows = db.query(TeamContact).filter(TeamContact.is_active.is_(True),
                                        TeamContact.role.in_(FULL_PREVIEW_ROLES)).all()
    return [r.email for r in rows if r.email]


def rep_email_for(db: Session, jn_name: str | None) -> str:
    """Where a rep's own-customers preview goes (active reps only)."""
    return rep_contact(db, jn_name)["rep_email"]


def normalize_phone(raw: str | None) -> str | None:
    digits = re.sub(r"\D", "", raw or "")[-10:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}" if len(digits) == 10 else None
