"""
Crew matching service.

Matches the best crews to the most complex jobs per PM.
Per client request: "Michael Jordan in first" — top-ranked crews get hardest jobs.

Key concepts:
- Each job gets a complexity score (higher = harder / more expensive).
- Each crew has a rank (1 = best, higher = bench players).
- For each PM's assigned jobs, we rank jobs by complexity and crews by rank,
  then pair them — hardest job → best crew.
- Specialty materials (slate, TPO, etc.) require a crew with matching specialty.
- Crew availability per day: each crew can only be assigned to one job per day.
"""
from sqlalchemy.orm import Session

from backend.models.job import Job, LOW_SLOPE_MATERIALS, SPECIALTY_MATERIALS
from backend.models.pm import Crew


# Materials that REQUIRE a specialty crew (hard gate)
SPECIALTY_MATERIAL_VALUES = {m.value for m in SPECIALTY_MATERIALS}  # wood_shake, slate, metal
LOW_SLOPE_MATERIAL_VALUES = {m.value for m in LOW_SLOPE_MATERIALS}  # tpo, duro_last, epdm, coating


def compute_complexity_score(job_dict: dict) -> float:
    """
    Compute a complexity score for a job.
    Higher = harder / more expensive / "pain in the ass" per client language.
    Uses job data from the scoring result dict.
    """
    score = 0.0

    # Must-Build = high stakes, need top crew
    if job_dict.get("must_build"):
        score += 50

    # Material complexity
    mat = (job_dict.get("material_type") or "").lower()
    if mat in LOW_SLOPE_MATERIAL_VALUES:
        score += 40  # Low slope jobs consume full days, high failure cost
    elif mat in SPECIALTY_MATERIAL_VALUES:
        score += 30  # Wood shake, slate, metal — specialty work

    # Duration tier (larger roofs = more complex)
    tier = (job_dict.get("duration_tier") or "").lower()
    if tier == "tier_3":
        score += 25
    elif tier == "tier_2":
        score += 10
    elif tier == "low_slope":
        score += 20

    # Crew requirement flag (set on specialty materials already, but also standalone flag)
    # Note: already implied by SPECIALTY_MATERIAL_VALUES above but we keep it
    # for cases where the flag was set manually by the scheduler.

    # Multi-day = more complex to coordinate
    if job_dict.get("is_multi_day"):
        score += 15

    # Standalone = isolated, harder to support
    if job_dict.get("standalone_rule"):
        score += 10

    return score


def _trade_matches(crew: Crew, primary_trade: str) -> bool:
    """
    Does this crew's trade scope include this job's trade?
    - If the job's primary_trade is missing → lenient, any crew matches (Q1=A)
    - If the crew has no trades configured → strict, no match (Q4=B)
    - Otherwise: crew.trades must contain primary_trade
    """
    if not primary_trade or primary_trade == "other":
        # Q1=A — lenient on data quality. Jobs without a real trade can match any crew.
        return True
    crew_trades = {t.lower() for t in (crew.trades or [])}
    if not crew_trades:
        # Q4=B — empty trades = broken crew config = no match
        return False
    return primary_trade.lower() in crew_trades


def _material_matches(crew: Crew, material: str) -> bool:
    """Does this crew have the material specialty needed?"""
    if not material:
        return True
    mat = material.lower()
    specialties = {s.lower() for s in (crew.specialties or [])}

    # Specialty materials (slate, wood_shake, metal) require the matching specialty
    if mat in SPECIALTY_MATERIAL_VALUES:
        return mat in specialties
    if mat in LOW_SLOPE_MATERIAL_VALUES:
        return mat in specialties or "low_slope" in specialties or "tpo" in specialties
    # Standard materials (asphalt, polymer_modified, or empty/siding) — no specialty gate
    return True


def _crew_eligible_for(crew: Crew, job: dict) -> bool:
    """
    Trade-aware eligibility check.
    Step 1: Trade gate — crew.trades must include job.primary_trade (Q4=B: empty trades fails)
    Step 2: Material gate — crew must have specialty for slate/tpo/etc.
    """
    primary_trade = (job.get("primary_trade") or "").lower()
    if not _trade_matches(crew, primary_trade):
        return False
    material = (job.get("material_type") or "").lower()
    return _material_matches(crew, material)


def match_crews_to_pm_jobs(db: Session, pm_plan: list[dict]) -> list[dict]:
    """
    For each PM's jobs, pair the best available crews with the most complex jobs.
    Trade-aware: a roofing-only crew is never assigned to a siding job and vice versa.
    Mutates each job in pm_plan[].jobs[] to include:
      - complexity_score (float)
      - suggested_crew_id (int or None)
      - suggested_crew_name (str or None)
      - suggested_crew_rank (int or None)
      - crew_warning (str or None) — if no suitable crew found

    Returns the mutated pm_plan.
    """
    active_crews = db.query(Crew).filter(Crew.is_active == True).order_by(  # noqa: E712
        Crew.rank.asc(), Crew.name.asc()
    ).all()

    # Track crews already assigned (one crew = one job per scoring run, matching "day" reality)
    used_crew_ids: set[int] = set()

    # Pre-compute which trades the active crew pool actually covers (for diagnostic warnings)
    trades_in_pool: set[str] = set()
    for c in active_crews:
        for t in (c.trades or []):
            if t:
                trades_in_pool.add(t.lower())

    for pm in pm_plan:
        jobs = pm.get("jobs", [])
        if not jobs:
            continue

        # Compute complexity for each job
        for job in jobs:
            job["complexity_score"] = compute_complexity_score(job)

        # Sort jobs by complexity descending (hardest first). The hardest job
        # gets first pick of crews — even multi-trade crews. This naturally
        # leaves trade-restricted crews available for their own trade jobs.
        jobs_sorted = sorted(jobs, key=lambda j: -j["complexity_score"])

        # Assign crews in complexity order
        for job in jobs_sorted:
            primary_trade = (job.get("primary_trade") or "").lower()
            material = (job.get("material_type") or "").lower()
            best_crew = None

            # Find highest-ranked available crew that's eligible for this job
            for crew in active_crews:
                if crew.id in used_crew_ids:
                    continue
                if _crew_eligible_for(crew, job):
                    best_crew = crew
                    break

            if best_crew:
                job["suggested_crew_id"] = best_crew.id
                job["suggested_crew_name"] = best_crew.name
                job["suggested_crew_rank"] = best_crew.rank
                job["crew_warning"] = None
                used_crew_ids.add(best_crew.id)
            else:
                job["suggested_crew_id"] = None
                job["suggested_crew_name"] = None
                job["suggested_crew_rank"] = None

                # Build a specific warning to help the scheduler diagnose
                if primary_trade and primary_trade != "other" and primary_trade not in trades_in_pool:
                    # No active crew works on this trade at all (Q2=A: strict gating)
                    job["crew_warning"] = f"No active {primary_trade} crew available"
                elif material in SPECIALTY_MATERIAL_VALUES:
                    job["crew_warning"] = f"No active {material} specialty crew available"
                elif material in LOW_SLOPE_MATERIAL_VALUES:
                    job["crew_warning"] = f"No active {material} / low-slope crew available"
                elif len(used_crew_ids) >= len(active_crews):
                    job["crew_warning"] = "All active crews assigned; this job needs another day"
                else:
                    job["crew_warning"] = "No suitable crew found (check trade + specialty)"

    return pm_plan


def build_crew_context_for_claude(db: Session) -> list[dict]:
    """
    Build crew context for the AI scoring prompt.
    Returns ranked crews with trades, specialties, and notes so Claude can reason
    about 'Michael Jordan on the hard job' AND match the right trade pool.
    """
    crews = db.query(Crew).filter(Crew.is_active == True).order_by(  # noqa: E712
        Crew.rank.asc(), Crew.name.asc()
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "rank": c.rank,
            # Trades drive HARD assignment gating — roofing crews never get siding jobs
            "trades": c.trades or [],
            # Materials are softer specialty constraints (slate, tpo, wood_shake)
            "specialties": c.specialties or [],
            "notes": c.notes or "",
        }
        for c in crews
    ]
