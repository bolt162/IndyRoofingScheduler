"""
AI Scoring Engine — Hybrid approach.
1. Deterministic scoring: weighted numeric scores for each factor
2. Claude API layer: interprets plain-English rules and adjusts recommendations
3. Fallback: if Claude fails, deterministic scores are used alone
4. Cost controls: top-N filtering, crew/weather/proximity data sent to Claude
"""
import json
from datetime import datetime, date

import anthropic
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job, JobBucket
from backend.models.pm import PM, Crew
from backend.models.settings import SystemSettings


def _get_setting(db: Session, key: str, default: str = "0") -> str:
    s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return s.value if s else default


def _get_weight(db: Session, key: str) -> float:
    return float(_get_setting(db, key, "10"))


def compute_deterministic_score(job: Job, db: Session) -> tuple[float, list[str]]:
    """Compute a deterministic score for a job based on weighted factors."""
    score = 0.0
    explanations = []

    # 1. Days in queue vs rolling average
    avg_days = float(_get_setting(db, "sit_time_rolling_avg_days", "38"))
    weight_queue = _get_weight(db, "weight_days_in_queue")
    days_in_queue = 0
    if job.date_entered:
        days_in_queue = (datetime.utcnow() - job.date_entered).days
    if avg_days > 0:
        queue_factor = (days_in_queue / avg_days) * weight_queue
    else:
        queue_factor = 0
    score += queue_factor
    explanations.append(f"Queue: {days_in_queue}d (avg {avg_days:.0f}d) -> +{queue_factor:.1f}")

    # 2. Payment type
    weight_payment = _get_weight(db, "weight_payment_type")
    payment_scores = {"cash": 1.0, "finance": 0.7, "insurance": 0.4}
    pt = (job.payment_type or "").lower()
    payment_factor = payment_scores.get(pt, 0.5) * weight_payment
    score += payment_factor
    explanations.append(f"Payment ({pt or 'unknown'}): +{payment_factor:.1f}")

    # 3. Trade complexity
    weight_trade = _get_weight(db, "weight_trade_complexity")
    is_single = not job.secondary_trades or len(job.secondary_trades) == 0
    trade_factor = weight_trade if is_single else weight_trade * 0.5
    score += trade_factor
    explanations.append(f"Trade ({'single' if is_single else 'multi'}): +{trade_factor:.1f}")

    # 4. Permit confirmed
    weight_permit = _get_weight(db, "weight_permit_confirmed")
    if job.permit_confirmed:
        score += weight_permit
        explanations.append(f"Permit confirmed: +{weight_permit:.1f}")

    # 5. Duration confirmed
    weight_duration = _get_weight(db, "weight_duration_confirmed")
    if job.duration_confirmed:
        score += weight_duration
        explanations.append(f"Duration confirmed: +{weight_duration:.1f}")

    # 6. Rescheduled counter bump
    weight_resched = _get_weight(db, "weight_rescheduled")
    if job.rescheduled_count > 0:
        resched_factor = min(job.rescheduled_count * (weight_resched / 3), weight_resched * 2)
        score += resched_factor
        explanations.append(f"Rescheduled {job.rescheduled_count}x: +{resched_factor:.1f}")

    # 7. Priority bump (from Not Built displaced jobs)
    if job.priority_bump > 0:
        score += job.priority_bump
        explanations.append(f"Priority bump: +{job.priority_bump:.1f}")

    # Must-Build override
    if job.must_build:
        score = 9999.0
        explanations.insert(0, "MUST-BUILD: score overridden to maximum")

    return score, explanations


def run_scoring_engine(db: Session, pm_ids: list[int] | None = None, target_date: str | None = None) -> dict:
    """Run the full scoring engine on all To Schedule jobs."""
    jobs = db.query(Job).filter(Job.bucket == JobBucket.TO_SCHEDULE.value).all()
    if not jobs:
        return {"recommendations": [], "clusters": [], "ai_explanation": "No jobs in To Schedule queue."}

    # Get available PMs
    if pm_ids:
        pms = db.query(PM).filter(PM.id.in_(pm_ids), PM.is_active == True).all()
    else:
        pms = db.query(PM).filter(PM.is_active == True).all()

    # Get available crews
    crews = db.query(Crew).filter(Crew.is_active == True).all()

    # Step 1: Deterministic scoring
    scored_jobs = []
    for job in jobs:
        score, explanations = compute_deterministic_score(job, db)
        job.score = score
        job.score_explanation = "; ".join(explanations)
        db.commit()
        scored_jobs.append({
            "job_id": job.id,
            "customer_name": job.customer_name,
            "address": job.address,
            "score": score,
            "explanation": "; ".join(explanations),
            "payment_type": job.payment_type,
            "material_type": job.material_type,
            "primary_trade": job.primary_trade,
            "secondary_trades": job.secondary_trades or [],
            "days_in_queue": (datetime.utcnow() - job.date_entered).days if job.date_entered else 0,
            "must_build": job.must_build,
            "must_build_deadline": str(job.must_build_deadline) if job.must_build_deadline else None,
            "duration_days": job.duration_days,
            "duration_confirmed": job.duration_confirmed,
            "duration_tier": job.duration_tier,
            "latitude": job.latitude,
            "longitude": job.longitude,
            "rescheduled_count": job.rescheduled_count,
            "standalone_rule": job.standalone_rule,
            "is_multi_day": job.is_multi_day,
            "weather_status": job.weather_status,
            "weather_detail": job.weather_detail,
        })

    scored_jobs.sort(key=lambda x: x["score"], reverse=True)

    # Step 2: Try Claude for plain-English rule interpretation
    # Cost control: only send top 50 candidates to Claude
    custom_rules = _get_setting(db, "ai_custom_rules", "")
    ai_explanation = "Deterministic scoring applied."
    max_claude_jobs = 50

    if settings.ANTHROPIC_API_KEY and custom_rules.strip():
        try:
            top_jobs = scored_jobs[:max_claude_jobs]
            # Build proximity matrix for top jobs only
            proximity_data = _build_proximity_summary(top_jobs)
            # Get weather forecast summary
            weather_summary = _build_weather_summary(top_jobs)
            # Build crew info
            crew_data = [{"name": c.name, "specialties": c.specialties or []} for c in crews]

            ai_result = _run_claude_scoring(
                top_jobs, pms, crews=crew_data, custom_rules=custom_rules,
                target_date=target_date, proximity=proximity_data,
                weather_summary=weather_summary,
            )
            if ai_result:
                ai_explanation = ai_result.get("explanation", ai_explanation)
                adjustments = ai_result.get("adjustments", [])
                for adj in adjustments:
                    for sj in scored_jobs:
                        if sj["job_id"] == adj.get("job_id"):
                            sj["score"] += adj.get("score_adjustment", 0)
                            sj["explanation"] += f"; AI: {adj.get('reason', '')}"
                scored_jobs.sort(key=lambda x: x["score"], reverse=True)
        except Exception as e:
            ai_explanation = f"AI scoring unavailable (fallback to deterministic): {str(e)}"

    return {
        "recommendations": scored_jobs,
        "clusters": [],
        "ai_explanation": ai_explanation,
        "pm_count": len(pms),
        "job_count": len(scored_jobs),
    }


def _build_proximity_summary(scored_jobs: list[dict]) -> list[dict]:
    """Build a simplified proximity summary for Claude (nearby job pairs)."""
    from backend.services.clustering import haversine_miles

    nearby = []
    for i, j1 in enumerate(scored_jobs):
        if not j1.get("latitude") or not j1.get("longitude"):
            continue
        for j2 in scored_jobs[i + 1:]:
            if not j2.get("latitude") or not j2.get("longitude"):
                continue
            dist = haversine_miles(j1["latitude"], j1["longitude"], j2["latitude"], j2["longitude"]) * 1.3
            if dist <= 15:  # Only include nearby pairs
                nearby.append({
                    "job_a": j1["job_id"],
                    "job_b": j2["job_id"],
                    "approx_miles": round(dist, 1),
                })
    return nearby


def _build_weather_summary(scored_jobs: list[dict]) -> list[dict]:
    """Summarize weather status for jobs that have it."""
    return [
        {
            "job_id": j["job_id"],
            "weather_status": j.get("weather_status", "unknown"),
            "weather_detail": j.get("weather_detail", ""),
        }
        for j in scored_jobs
        if j.get("weather_status")
    ]


def _run_claude_scoring(
    scored_jobs: list[dict],
    pms: list,
    crews: list[dict] | None = None,
    custom_rules: str = "",
    target_date: str | None = None,
    proximity: list[dict] | None = None,
    weather_summary: list[dict] | None = None,
) -> dict | None:
    """Send job data and custom rules to Claude for AI-powered adjustments."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build context sections
    crew_section = ""
    if crews:
        crew_section = f"\nAVAILABLE CREWS ({len(crews)}):\n{json.dumps(crews, indent=2)}\n"

    proximity_section = ""
    if proximity:
        proximity_section = f"\nNEARBY JOB PAIRS (within 15 miles):\n{json.dumps(proximity, indent=2)}\n"

    weather_section = ""
    if weather_summary:
        weather_section = f"\nWEATHER STATUS FOR JOBS:\n{json.dumps(weather_summary, indent=2)}\n"

    pm_details = json.dumps([
        {"name": pm.name, "baseline_capacity": pm.baseline_capacity, "max_capacity": pm.max_capacity}
        for pm in pms
    ], indent=2)

    prompt = f"""You are the AI scoring engine for a roofing company's scheduling system.

You have been given a list of jobs already scored by deterministic factors. Your role is to interpret
the following plain-English custom rules and suggest score adjustments.

CUSTOM RULES FROM OPS TEAM:
{custom_rules}

CURRENT JOB QUEUE (top {len(scored_jobs)} candidates, already scored):
{json.dumps(scored_jobs, indent=2, default=str)}

AVAILABLE PMs ({len(pms)}):
{pm_details}
{crew_section}{proximity_section}{weather_section}
TARGET DATE: {target_date or 'next available'}

Instructions:
1. Review each custom rule against the job queue
2. Consider crew specialties when evaluating trade requirements
3. Factor in proximity data — jobs near each other should be scheduled together
4. Consider weather conditions — penalize jobs with bad weather forecasts
5. Return a JSON object with:
   - "adjustments": list of {{"job_id": int, "score_adjustment": float, "reason": str}}
   - "explanation": overall explanation of what rules were applied

Only return valid JSON. No markdown formatting.
Keep adjustments proportional (typically -10 to +10 range).
Be factual and objective in all explanations — these may be referenced in court-admissible notes.
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
    return None
