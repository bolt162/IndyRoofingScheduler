"""
AI Scoring Engine — Hybrid approach.
1. Weather pre-filter: incompatible jobs excluded before scoring (spec 3.2)
2. Proximity computation: nearby job counts via Google Maps driving distance
3. Deterministic scoring: weighted numeric scores for each factor
4. Claude API layer: interprets plain-English rules and adjusts recommendations
5. Fallback: if Claude fails, deterministic scores are used alone
6. Cost controls: top-N filtering, crew/weather/proximity data sent to Claude
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


def compute_deterministic_score(
    job: Job,
    db: Session,
    nearby_count: int = 0,
    weather_status: str | None = None,
) -> tuple[float, list[str]]:
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

    # 8. Geographic Proximity (spec 3.2: "Jobs that cluster tightly score higher")
    weight_proximity = _get_weight(db, "weight_proximity")
    if nearby_count > 0:
        # Saturates at 5 neighbors — matching tight cluster tier (up to 5 builds)
        proximity_factor = min(nearby_count / 5.0, 1.0) * weight_proximity
        score += proximity_factor
        explanations.append(f"Proximity ({nearby_count} nearby): +{proximity_factor:.1f}")

    # 9. Material-Weather Compatibility (spec 3.2: compatible jobs score higher)
    weight_weather = _get_weight(db, "weight_material_weather")
    if weather_status == "clear":
        score += weight_weather
        explanations.append(f"Weather (clear): +{weight_weather:.1f}")
    elif weather_status == "scheduler_decision":
        weather_factor = weight_weather * 0.3
        score += weather_factor
        explanations.append(f"Weather (marginal): +{weather_factor:.1f}")

    # Must-Build override — always last, supersedes everything
    if job.must_build:
        score = 9999.0
        explanations.insert(0, "MUST-BUILD: score overridden to maximum")

    return score, explanations


# ---------------------------------------------------------------------------
# Proximity computation
# ---------------------------------------------------------------------------

def _compute_nearby_counts(jobs: list[Job], db: Session) -> dict[int, int]:
    """
    Compute how many other jobs are within proximity radius for each job.
    Uses Google Maps driving distance (spec 5.4) with haversine fallback.
    """
    from backend.services.clustering import (
        haversine_miles,
        get_driving_distances_batch,
    )

    radius = float(_get_setting(db, "cluster_tier_3_miles", "10"))

    # Filter to jobs with coordinates
    geo_jobs = [(j, j.latitude, j.longitude) for j in jobs if j.latitude and j.longitude]
    counts: dict[int, int] = {j.id: 0 for j in jobs}

    if len(geo_jobs) < 2:
        return counts

    # Try Google Maps batch driving distances first
    coords = [(lat, lon) for _, lat, lon in geo_jobs]
    use_google = bool(settings.GOOGLE_MAPS_API_KEY)

    if use_google:
        batch_results = get_driving_distances_batch(coords, coords)
        for i in range(len(geo_jobs)):
            for j in range(i + 1, len(geo_jobs)):
                dist = batch_results.get((i, j)) or batch_results.get((j, i))
                if dist is None:
                    # Fallback for this pair if batch missed it
                    _, lat1, lon1 = geo_jobs[i]
                    _, lat2, lon2 = geo_jobs[j]
                    dist = haversine_miles(lat1, lon1, lat2, lon2) * 1.3
                if dist <= radius:
                    job1, _, _ = geo_jobs[i]
                    job2, _, _ = geo_jobs[j]
                    counts[job1.id] += 1
                    counts[job2.id] += 1
    else:
        # Pure haversine fallback (no API key)
        for i in range(len(geo_jobs)):
            job1, lat1, lon1 = geo_jobs[i]
            for j in range(i + 1, len(geo_jobs)):
                job2, lat2, lon2 = geo_jobs[j]
                dist = haversine_miles(lat1, lon1, lat2, lon2) * 1.3
                if dist <= radius:
                    counts[job1.id] += 1
                    counts[job2.id] += 1

    return counts


# ---------------------------------------------------------------------------
# Weather pre-filter
# ---------------------------------------------------------------------------

def _weather_prefilter(
    jobs: list[Job], db: Session, target_date: str
) -> tuple[list[Job], list[dict]]:
    """
    Pre-filter jobs by weather compatibility (spec 3.2).
    Returns (scorable_jobs, weather_blocked_list).
    Must-Build jobs are NEVER filtered — they override everything.
    """
    from backend.services.weather import get_forecast, check_material_thresholds

    scorable: list[Job] = []
    blocked: list[dict] = []

    # Cache forecasts by rounded lat/lon (~7mi granularity) to minimize API calls
    forecast_cache: dict[str, dict | None] = {}

    for job in jobs:
        # Must-Build jobs always pass through (spec 7.1: overrides all scoring)
        if job.must_build:
            scorable.append(job)
            continue

        # Jobs without coordinates can't be weather-checked — pass through
        if not (job.latitude and job.longitude):
            scorable.append(job)
            continue

        # Get forecast (cached by ~7mi area)
        cache_key = f"{round(job.latitude, 1)},{round(job.longitude, 1)}"
        if cache_key in forecast_cache:
            forecast = forecast_cache[cache_key]
        else:
            forecast = get_forecast(job.latitude, job.longitude, target_date)
            forecast_cache[cache_key] = forecast

        if not forecast:
            # API failure — safe default: pass through
            scorable.append(job)
            continue

        result = check_material_thresholds(db, job.material_type or "", forecast)
        job.weather_status = result["status"]
        job.weather_detail = result["detail"]

        if result["status"] == "do_not_build":
            blocked.append({
                "job_id": job.id,
                "customer_name": job.customer_name,
                "address": job.address,
                "material_type": job.material_type,
                "weather_status": "do_not_build",
                "weather_detail": result["detail"],
            })
        else:
            scorable.append(job)

    db.commit()
    return scorable, blocked


# ---------------------------------------------------------------------------
# PM assignment to clusters
# ---------------------------------------------------------------------------

def _assign_pms_to_clusters(
    raw_clusters: list[dict],
    pms: list,
    scored_jobs: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Assign PMs to clusters using a greedy capacity-based algorithm.
    Returns (enriched_clusters, pm_plan, unassigned_jobs).

    Per spec §5.1: max_capacity is a HARD CEILING — never exceeded.
    Per spec §5.2: cluster tier determines effective PM capacity:
      tight (≤1mi) → up to 5, close (≤2mi) → up to 4, standard (≤10mi) → 3,
      10-25mi → 2, 25-40mi → 1-2, >40mi → standalone (1).
    Jobs that don't fit any PM go to unassigned_jobs.
    """
    # Build scored_jobs lookup
    score_lookup = {sj["job_id"]: sj for sj in scored_jobs}

    # Enrich clusters with score info and job_ids
    enriched = []
    for c in raw_clusters:
        job_ids = [j["job_id"] for j in c["jobs"]]
        has_must_build = any(j.get("must_build") for j in c["jobs"])
        total_score = sum(score_lookup.get(jid, {}).get("score", 0) for jid in job_ids)
        enriched.append({
            "cluster_id": c["cluster_id"],
            "tier": c["tier"],
            "suggested_pm_capacity": c["suggested_pm_capacity"],
            "job_ids": job_ids,
            "total_score": total_score,
            "is_standalone": c.get("is_standalone", False),
            "has_must_build": has_must_build,
            "assigned_pm_id": None,
            "assigned_pm_name": None,
            "distances": c.get("distances", []),
        })

    # Sort: must-build clusters first, then by total score
    enriched.sort(key=lambda c: (not c["has_must_build"], -c["total_score"]))

    # PM capacity tracker
    if not pms:
        all_job_ids = set()
        for c in enriched:
            all_job_ids.update(c["job_ids"])
        unassigned = [score_lookup[jid] for jid in all_job_ids if jid in score_lookup]
        return enriched, [], unassigned

    pm_remaining = {}
    pm_assigned_jobs: dict[int, list[dict]] = {}
    pm_assigned_clusters: dict[int, list[str]] = {}
    for pm in sorted(pms, key=lambda p: p.baseline_capacity, reverse=True):
        pm_remaining[pm.id] = pm.max_capacity
        pm_assigned_jobs[pm.id] = []
        pm_assigned_clusters[pm.id] = []

    unassigned_job_ids: list[int] = []

    # Greedy assignment — respects both cluster tier capacity and PM max ceiling
    for cluster in enriched:
        cluster_job_ids = list(cluster["job_ids"])
        tier_capacity = cluster["suggested_pm_capacity"]  # From cluster tier (spec §5.2)

        # How many jobs from this cluster should one PM handle?
        # Limited by the tier's suggested capacity
        jobs_for_pm = cluster_job_ids[:tier_capacity]
        overflow_from_tier = cluster_job_ids[tier_capacity:]

        # Find PM with most remaining capacity that can fit jobs_for_pm
        best_pm = None
        best_remaining = -1
        for pm in pms:
            remaining = pm_remaining.get(pm.id, 0)
            if remaining >= len(jobs_for_pm) and remaining > best_remaining:
                best_pm = pm
                best_remaining = remaining

        if best_pm is None:
            # No PM can fit the full tier allocation — find PM with most space
            # but only assign what they can actually take (hard ceiling)
            for pm in pms:
                remaining = pm_remaining.get(pm.id, 0)
                if remaining > 0 and remaining > best_remaining:
                    best_pm = pm
                    best_remaining = remaining

        if best_pm and pm_remaining.get(best_pm.id, 0) > 0:
            # Only assign up to PM's remaining capacity (hard ceiling per spec §5.1)
            can_take = min(len(jobs_for_pm), pm_remaining[best_pm.id])
            assigned_ids = jobs_for_pm[:can_take]
            leftover_ids = jobs_for_pm[can_take:]

            cluster["assigned_pm_id"] = best_pm.id
            cluster["assigned_pm_name"] = best_pm.name
            pm_remaining[best_pm.id] -= len(assigned_ids)
            pm_assigned_clusters[best_pm.id].append(cluster["cluster_id"])
            for jid in assigned_ids:
                if jid in score_lookup:
                    job_entry = score_lookup[jid].copy()
                    job_entry["cluster_id"] = cluster["cluster_id"]
                    pm_assigned_jobs[best_pm.id].append(job_entry)

            # Jobs that exceeded PM's capacity go to unassigned
            unassigned_job_ids.extend(leftover_ids)
        else:
            # No PM has any remaining capacity — all go to unassigned
            unassigned_job_ids.extend(jobs_for_pm)

        # Jobs that exceeded the tier capacity go to unassigned
        # (could be assigned to another PM in a future iteration, but for now overflow)
        unassigned_job_ids.extend(overflow_from_tier)

    # Build pm_plan response
    pm_plan = []
    for pm in pms:
        assigned = pm_assigned_jobs.get(pm.id, [])
        assigned_count = len(assigned)
        pm_plan.append({
            "pm_id": pm.id,
            "pm_name": pm.name,
            "baseline_capacity": pm.baseline_capacity,
            "max_capacity": pm.max_capacity,
            "assigned_jobs": assigned_count,
            "clusters": pm_assigned_clusters.get(pm.id, []),
            "utilization": round(assigned_count / pm.baseline_capacity, 2) if pm.baseline_capacity > 0 else 0,
            "over_baseline": assigned_count > pm.baseline_capacity,
            "over_max": assigned_count > pm.max_capacity,
            "jobs": assigned,
        })

    # Build unassigned list (deduplicated)
    seen = set()
    unassigned = []
    for jid in unassigned_job_ids:
        if jid not in seen and jid in score_lookup:
            seen.add(jid)
            unassigned.append(score_lookup[jid])

    return enriched, pm_plan, unassigned


# ---------------------------------------------------------------------------
# Main scoring engine
# ---------------------------------------------------------------------------

def run_scoring_engine(db: Session, pm_ids: list[int] | None = None, target_date: str | None = None) -> dict:
    """Run the full scoring engine on all To Schedule jobs."""
    jobs = db.query(Job).filter(Job.bucket == JobBucket.TO_SCHEDULE.value).all()
    if not jobs:
        return {
            "recommendations": [], "clusters": [], "ai_explanation": "No jobs in To Schedule queue.",
            "weather_blocked": [], "weather_blocked_count": 0,
        }

    # Get available PMs
    if pm_ids:
        pms = db.query(PM).filter(PM.id.in_(pm_ids), PM.is_active == True).all()
    else:
        pms = db.query(PM).filter(PM.is_active == True).all()

    # Get available crews
    crews = db.query(Crew).filter(Crew.is_active == True).all()

    # --- Step 1: Weather pre-filter (spec 3.2: "Incompatible jobs are filtered before scoring") ---
    weather_blocked: list[dict] = []
    if target_date:
        scorable_jobs, weather_blocked = _weather_prefilter(jobs, db, target_date)
    else:
        scorable_jobs = jobs

    if not scorable_jobs:
        return {
            "recommendations": [],
            "clusters": [],
            "ai_explanation": "All jobs filtered out by weather. No buildable jobs for this date.",
            "weather_blocked": weather_blocked,
            "weather_blocked_count": len(weather_blocked),
            "pm_count": len(pms),
            "job_count": 0,
        }

    # --- Step 2: Compute proximity counts (spec 3.2: "Jobs that cluster tightly score higher") ---
    nearby_counts = _compute_nearby_counts(scorable_jobs, db)

    # --- Step 3: Deterministic scoring with proximity + weather factors ---
    scored_jobs = []
    for job in scorable_jobs:
        score, explanations = compute_deterministic_score(
            job, db,
            nearby_count=nearby_counts.get(job.id, 0),
            weather_status=job.weather_status if target_date else None,
        )
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

    # --- Step 4: Claude AI layer (spec 3.1: always runs to explain recommendations) ---
    custom_rules = _get_setting(db, "ai_custom_rules", "")
    ai_explanation = "Deterministic scoring applied."
    max_claude_jobs = 50

    if settings.ANTHROPIC_API_KEY:
        try:
            top_jobs = scored_jobs[:max_claude_jobs]
            proximity_data = _build_proximity_summary(top_jobs)
            weather_summary = _build_weather_summary(top_jobs)
            crew_data = [{"name": c.name, "specialties": c.specialties or []} for c in crews]
            sit_time_avg = float(_get_setting(db, "sit_time_rolling_avg_days", "38"))

            ai_result = _run_claude_scoring(
                top_jobs, pms, crews=crew_data, custom_rules=custom_rules,
                target_date=target_date, proximity=proximity_data,
                weather_summary=weather_summary,
                sit_time_avg=sit_time_avg,
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

    # --- Step 5: Clustering + PM assignment (spec 3.4: "grouped by PM with cluster map") ---
    from backend.services.clustering import cluster_jobs as _cluster_jobs

    raw_clusters = _cluster_jobs(db)
    clusters_enriched, pm_plan, unassigned = _assign_pms_to_clusters(
        raw_clusters, pms, scored_jobs,
    )

    # Enrich scored_jobs with cluster_id and suggested_pm_id
    job_cluster_map: dict[int, tuple[str, int | None]] = {}
    for c in clusters_enriched:
        for jid in c["job_ids"]:
            job_cluster_map[jid] = (c["cluster_id"], c.get("assigned_pm_id"))
    for sj in scored_jobs:
        cid, pm_id = job_cluster_map.get(sj["job_id"], (None, None))
        sj["cluster_id"] = cid
        sj["suggested_pm_id"] = pm_id

    return {
        "recommendations": scored_jobs,
        "clusters": clusters_enriched,
        "pm_plan": pm_plan,
        "unassigned_jobs": unassigned,
        "ai_explanation": ai_explanation,
        "weather_blocked": weather_blocked,
        "weather_blocked_count": len(weather_blocked),
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
    sit_time_avg: float = 38.0,
) -> dict | None:
    """
    Send full job queue context to Claude for AI-powered analysis and adjustments.
    Per spec §3.1: "The AI receives the full job queue, available crew and PM inputs,
    configured rules, and weather data, then returns ranked recommendations with
    written explanations."
    Always runs — custom rules are additional context, not a prerequisite.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    # Build context sections
    crew_section = ""
    if crews:
        crew_section = f"\nAVAILABLE CREWS ({len(crews)}):\n{json.dumps(crews, indent=2)}\n"

    proximity_section = ""
    if proximity:
        proximity_section = f"\nNEARBY JOB PAIRS (driving distance within 15 miles):\n{json.dumps(proximity, indent=2)}\n"
    else:
        proximity_section = "\nNEARBY JOB PAIRS: No jobs within 15 miles of each other.\n"

    weather_section = ""
    if weather_summary:
        weather_section = f"\nWEATHER STATUS FOR JOBS:\n{json.dumps(weather_summary, indent=2)}\n"

    custom_rules_section = ""
    if custom_rules.strip():
        custom_rules_section = f"\nCUSTOM RULES FROM OPS TEAM (apply these on top of standard scoring):\n{custom_rules}\n"
    else:
        custom_rules_section = "\nCUSTOM RULES: None configured. Apply standard scoring logic only.\n"

    pm_details = json.dumps([
        {"name": pm.name, "baseline_capacity": pm.baseline_capacity, "max_capacity": pm.max_capacity}
        for pm in pms
    ], indent=2)

    # Build must-build summary
    must_builds = [j for j in scored_jobs if j.get("must_build")]
    must_build_section = ""
    if must_builds:
        mb_info = [f"- {j['customer_name']} (deadline: {j.get('must_build_deadline', 'none')})" for j in must_builds]
        must_build_section = f"\nMUST-BUILD JOBS (override all scoring, anchor first):\n" + "\n".join(mb_info) + "\n"

    prompt = f"""You are the AI scoring engine for Indy Roof & Restoration's scheduling system.

Your job is to analyze the full job queue, explain the scoring strategy, identify geographic clusters,
and suggest any score adjustments. You ALWAYS provide a comprehensive explanation — the scheduler
needs to understand the full picture at a glance.

CONTEXT:
- Rolling average sit time: {sit_time_avg:.0f} days
- Target date: {target_date or 'next available'}
- {len(scored_jobs)} jobs in scoring queue
- {len(pms)} PMs available

CURRENT JOB QUEUE (already scored by deterministic factors):
{json.dumps(scored_jobs, indent=2, default=str)}

AVAILABLE PMs ({len(pms)}):
{pm_details}
{crew_section}{proximity_section}{weather_section}{must_build_section}{custom_rules_section}
INSTRUCTIONS:
1. Analyze the job queue and provide a strategic overview:
   - How many geographic clusters exist and where (use addresses to identify areas)
   - Which jobs are high priority and why (long queue time, cash payment, must-build)
   - Any concerns (unconfirmed durations, standalone jobs, weather risks)
2. If custom rules are configured, apply them and note any adjustments
3. Consider proximity — jobs near each other should be scheduled on the same day for PM efficiency
4. Note any jobs that seem risky to schedule (unconfirmed Tier 3, weather marginal)

Return a JSON object with:
- "explanation": A 3-5 sentence executive summary covering: scoring strategy, clusters found,
  PM assignment rationale, any custom rule applications, and key concerns. Write as if briefing
  the scheduling team. Be specific — mention customer names, areas, and distances.
- "adjustments": list of {{"job_id": int, "score_adjustment": float, "reason": str}}
  Only include adjustments if custom rules or proximity analysis warrants changing scores.
  Empty list is fine if deterministic scores are sufficient.

Only return valid JSON. No markdown formatting.
Keep adjustments proportional (typically -10 to +10 range).
Be factual and objective — these explanations may be referenced in court-admissible notes.
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
