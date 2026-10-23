"""
Geocoding: turns a job's address into a map spot (lat, lng).

Same lookup the instant quote and the website's projects map use, so a home that's found there is found here:
the quote's address search first (every Indiana address point plus the state parcel map; handles Rd/Ct/Ln,
"County Road 144" vs "State Road 144", unit numbers and extra town words), then Google (good with misspellings
and nicknames like "Indy"), then the US Census address finder (free, no key). A spot outside Indiana is never used.
"""
import httpx
from backend.config import settings

QUOTE_SEARCH = "https://quote.indyroofandrestoration.com/api/address"
CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def in_indiana(lat, lng) -> bool:
    """JobNimbus sends 0,0 when it couldn't place a home; that (or anything else outside Indiana) is no spot."""
    return bool(lat and lng) and 37.7 < lat < 41.8 and -88.2 < lng < -84.7


def _quote(address: str):
    resp = httpx.get(QUOTE_SEARCH, params={"q": address[:200]}, timeout=8)
    resp.raise_for_status()
    hits = resp.json()
    return (hits[0]["lat"], hits[0]["lng"]) if hits else None


def _google(address: str):
    if not settings.GOOGLE_MAPS_API_KEY:
        return None
    data = httpx.get("https://maps.googleapis.com/maps/api/geocode/json", timeout=10,
                     params={"address": address, "components": "country:US",
                             "key": settings.GOOGLE_MAPS_API_KEY}).json()
    if data.get("status") == "OK" and data.get("results"):
        location = data["results"][0]["geometry"]["location"]
        return (location["lat"], location["lng"])
    return None


def _census(address: str):
    data = httpx.get(CENSUS, timeout=8, params={"address": address, "benchmark": "Public_AR_Current",
                                                 "format": "json"}).json()
    match = (data.get("result", {}).get("addressMatches") or [None])[0]
    return (match["coordinates"]["y"], match["coordinates"]["x"]) if match else None


LOOKUPS = (_quote, _google, _census)


def geocode_address(address: str) -> tuple[float, float] | None:
    """(latitude, longitude) for an address, or None when no lookup can place it in Indiana."""
    if not address or not address.strip():
        return None
    for lookup in LOOKUPS:
        try:
            spot = lookup(address.strip())
        except Exception:
            spot = None  # that service is down or busy: try the next one
        if spot and in_indiana(*spot):
            return spot
    return None


def place_job(job, jn_lat=None, jn_lng=None) -> bool:
    """Put a synced job on the map with our lookup, once per address. JobNimbus's own pin is only the backup
    (it's sometimes 0,0 or a mile or two off). Returns True when a lookup ran."""
    if job.geocoded_address == job.address and in_indiana(job.latitude, job.longitude):
        return False
    spot = geocode_address(job.address)
    if spot:
        job.latitude, job.longitude = spot
        job.geocoded_address = job.address
    elif in_indiana(jn_lat, jn_lng):
        job.latitude, job.longitude = jn_lat, jn_lng  # tried again next sync
    return True
