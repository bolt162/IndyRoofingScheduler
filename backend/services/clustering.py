"""
Geographic clustering service.
Uses Google Maps Distance Matrix API for driving distance calculations.
Lat/lng coordinates come directly from JobNimbus — no geocoding needed.
Falls back to haversine * 1.3 when Google Maps API is unavailable.
Caches distance results in-memory to minimize API calls.
"""
import math
import httpx
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.job import Job, JobBucket
from backend.models.settings import SystemSettings


# In-memory distance cache: key = "lat1,lng1|lat2,lng2" -> miles
_distance_cache: dict[str, float] = {}


def _get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(SystemSettings).filter(SystemSettings.key == key).first()
    return s.value if s else default


def _cache_key(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Create a symmetric cache key (A->B == B->A)."""
    pair = sorted([(lat1, lon1), (lat2, lon2)])
    return f"{pair[0][0]:.6f},{pair[0][1]:.6f}|{pair[1][0]:.6f},{pair[1][1]:.6f}"


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance in miles between two coordinates."""
    R = 3959  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def get_driving_distance(origin: tuple[float, float], destination: tuple[float, float]) -> float | None:
    """Get driving distance in miles using Google Maps Distance Matrix API. Results are cached."""
    if not settings.GOOGLE_MAPS_API_KEY:
        return None

    # Check cache first
    key = _cache_key(origin[0], origin[1], destination[0], destination[1])
    if key in _distance_cache:
        return _distance_cache[key]

    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": f"{origin[0]},{origin[1]}",
        "destinations": f"{destination[0]},{destination[1]}",
        "units": "imperial",
        "key": settings.GOOGLE_MAPS_API_KEY,
    }

    try:
        resp = httpx.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "OK":
            element = data["rows"][0]["elements"][0]
            if element["status"] == "OK":
                meters = element["distance"]["value"]
                miles = meters * 0.000621371
                _distance_cache[key] = miles
                return miles
    except Exception:
        pass
    return None


def get_driving_distances_batch(
    origins: list[tuple[float, float]],
    destinations: list[tuple[float, float]],
) -> dict[tuple[int, int], float]:
    """
    Batch distance lookup using Google Maps Distance Matrix API.
    Sends up to 25 origins x 25 destinations per call (API limit).
    Returns dict mapping (origin_idx, dest_idx) -> miles.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        return {}

    results = {}
    # Check cache and find uncached pairs
    uncached_origins = set()
    uncached_dests = set()
    for i, o in enumerate(origins):
        for j, d in enumerate(destinations):
            if i == j:
                continue
            key = _cache_key(o[0], o[1], d[0], d[1])
            if key in _distance_cache:
                results[(i, j)] = _distance_cache[key]
            else:
                uncached_origins.add(i)
                uncached_dests.add(j)

    if not uncached_origins:
        return results

    # Batch API call for uncached pairs (limit: 25x25 per request)
    origin_list = sorted(uncached_origins)
    dest_list = sorted(uncached_dests)

    for o_start in range(0, len(origin_list), 25):
        o_chunk = origin_list[o_start:o_start + 25]
        for d_start in range(0, len(dest_list), 25):
            d_chunk = dest_list[d_start:d_start + 25]

            origins_str = "|".join(f"{origins[i][0]},{origins[i][1]}" for i in o_chunk)
            dests_str = "|".join(f"{destinations[j][0]},{destinations[j][1]}" for j in d_chunk)

            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": origins_str,
                "destinations": dests_str,
                "units": "imperial",
                "key": settings.GOOGLE_MAPS_API_KEY,
            }

            try:
                resp = httpx.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data["status"] == "OK":
                    for row_idx, row in enumerate(data["rows"]):
                        for col_idx, element in enumerate(row["elements"]):
                            if element["status"] == "OK":
                                miles = element["distance"]["value"] * 0.000621371
                                oi = o_chunk[row_idx]
                                di = d_chunk[col_idx]
                                results[(oi, di)] = miles
                                key = _cache_key(origins[oi][0], origins[oi][1], destinations[di][0], destinations[di][1])
                                _distance_cache[key] = miles
            except Exception:
                pass

    return results


def get_distance(job1: Job, job2: Job) -> float:
    """Get distance between two jobs. Tries Google Maps first, falls back to haversine."""
    if not (job1.latitude and job1.longitude and job2.latitude and job2.longitude):
        return float("inf")

    driving = get_driving_distance(
        (job1.latitude, job1.longitude),
        (job2.latitude, job2.longitude),
    )
    if driving is not None:
        return driving

    return haversine_miles(job1.latitude, job1.longitude, job2.latitude, job2.longitude) * 1.3


def cluster_jobs(db: Session) -> list[dict]:
    """
    Cluster all To Schedule jobs by geographic proximity.
    Uses batch distance matrix calls when possible to minimize API costs.
    """
    jobs = db.query(Job).filter(
        Job.bucket == JobBucket.TO_SCHEDULE.value,
        Job.latitude != None,
        Job.longitude != None,
    ).all()

    if not jobs:
        return []

    # Pre-fetch all distances in one batch call (cost-efficient)
    coords = [(j.latitude, j.longitude) for j in jobs]
    batch_distances = get_driving_distances_batch(coords, coords)

    def _get_dist(i: int, j: int) -> float:
        if (i, j) in batch_distances:
            return batch_distances[(i, j)]
        if (j, i) in batch_distances:
            return batch_distances[(j, i)]
        return haversine_miles(coords[i][0], coords[i][1], coords[j][0], coords[j][1]) * 1.3

    # Get distance thresholds from settings
    tier_1 = float(_get_setting(db, "cluster_tier_1_miles", "1"))
    tier_2 = float(_get_setting(db, "cluster_tier_2_miles", "2"))
    tier_3 = float(_get_setting(db, "cluster_tier_3_miles", "10"))
    tier_5 = float(_get_setting(db, "cluster_tier_5_miles", "40"))

    job_indices = {j.id: idx for idx, j in enumerate(jobs)}

    remaining = sorted(jobs, key=lambda j: j.score, reverse=True)
    clusters = []
    assigned = set()

    while remaining:
        anchor = remaining[0]
        if anchor.id in assigned:
            remaining.pop(0)
            continue

        anchor_idx = job_indices[anchor.id]
        cluster_jobs_list = [anchor]
        assigned.add(anchor.id)
        cluster_distances = []

        for other in remaining[1:]:
            if other.id in assigned:
                continue
            other_idx = job_indices[other.id]
            dist = _get_dist(anchor_idx, other_idx)
            if dist <= tier_3:
                cluster_jobs_list.append(other)
                assigned.add(other.id)
                cluster_distances.append({"from": anchor.id, "to": other.id, "miles": round(dist, 2)})

        if cluster_distances:
            max_dist = max(d["miles"] for d in cluster_distances)
            if max_dist <= tier_1:
                tier_label = "tight"
                suggested_capacity = 5
            elif max_dist <= tier_2:
                tier_label = "close"
                suggested_capacity = 4
            else:
                tier_label = "standard"
                suggested_capacity = 3
        else:
            tier_label = "standalone"
            suggested_capacity = 1

        cluster = {
            "cluster_id": f"cluster_{len(clusters) + 1}",
            "tier": tier_label,
            "suggested_pm_capacity": suggested_capacity,
            "jobs": [
                {
                    "job_id": j.id,
                    "customer_name": j.customer_name,
                    "address": j.address,
                    "score": j.score,
                    "lat": j.latitude,
                    "lng": j.longitude,
                    "must_build": j.must_build,
                    "material_type": j.material_type,
                }
                for j in cluster_jobs_list
            ],
            "distances": cluster_distances,
            "is_standalone": len(cluster_jobs_list) == 1,
        }
        clusters.append(cluster)
        remaining = [j for j in remaining if j.id not in assigned]

    # Auto-flag standalone jobs
    for cluster in clusters:
        if cluster["is_standalone"]:
            job_id = cluster["jobs"][0]["job_id"]
            job = db.query(Job).filter(Job.id == job_id).first()
            if job and not job.standalone_rule:
                job.standalone_rule = True
                db.commit()

    return clusters


def get_proximity_matrix(db: Session) -> list[dict]:
    """Build a proximity matrix for all To Schedule jobs. Used by Claude scoring."""
    jobs = db.query(Job).filter(
        Job.bucket == JobBucket.TO_SCHEDULE.value,
        Job.latitude != None,
        Job.longitude != None,
    ).all()

    if len(jobs) < 2:
        return []

    coords = [(j.latitude, j.longitude) for j in jobs]
    batch = get_driving_distances_batch(coords, coords)

    matrix = []
    for i, j1 in enumerate(jobs):
        for j, j2 in enumerate(jobs):
            if i >= j:
                continue
            dist = batch.get((i, j)) or batch.get((j, i))
            if dist is None:
                dist = haversine_miles(coords[i][0], coords[i][1], coords[j][0], coords[j][1]) * 1.3
            matrix.append({
                "job_a": j1.id,
                "job_b": j2.id,
                "miles": round(dist, 2),
            })

    return matrix


def clear_distance_cache():
    """Clear the distance cache."""
    _distance_cache.clear()
