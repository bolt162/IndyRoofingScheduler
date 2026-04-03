"""
Geocoding utility — converts addresses to lat/lng via Google Maps Geocoding API.
Used for manually created jobs (JN jobs already have lat/lng from JN geo data).
"""
import httpx
from backend.config import settings


def geocode_address(address: str) -> tuple[float, float] | None:
    """
    Geocode an address string to (latitude, longitude) using Google Maps API.
    Returns None if geocoding fails or no API key is configured.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        return None

    if not address or not address.strip():
        return None

    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address.strip(),
            "key": settings.GOOGLE_MAPS_API_KEY,
        }
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("status") == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            return (location["lat"], location["lng"])
        return None
    except Exception:
        return None
