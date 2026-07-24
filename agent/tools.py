"""Tool boundary. Every external dependency (geocoding, place search,
weather, directions) is called through this module, and this module is the
single seam: TEST_MODE switches every function between fixture data and a
real implementation.

The real implementations below have not been exercised against a live
Google Maps Platform key yet (none was available while building this) —
they're written against the documented request/response shapes and covered
by tests using a mocked HTTP transport, but treat them as needing a first
live smoke test once GOOGLE_MAPS_API_KEY is actually set.
"""

from __future__ import annotations

import os

import httpx

from . import fixtures

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
_WEATHER_URL = "https://weather.googleapis.com/v1/forecast/days:lookup"
_PLACES_BASE_URL = "https://places.googleapis.com/v1"

_REQUEST_TIMEOUT_SECONDS = 10.0

# Preference category -> Places Text Search query term.
_CATEGORY_QUERY_TERM = {
    "museum": "museums",
    "nature": "parks and nature attractions",
    "food": "restaurants",
    "historic": "historic sites",
    "shopping": "shopping malls",
    "night_market": "night markets",
    "hiking": "hiking trails",
    "golf": "golf courses",
}

# Places `types` -> estimated visit duration in hours. Places API has no
# duration field, so this heuristic stands in for it (see spec.md section 4).
_DURATION_HEURISTIC_HR = {
    "museum": 1.5,
    "art_gallery": 1.5,
    "park": 1.5,
    "natural_feature": 1.5,
    "restaurant": 1.0,
    "cafe": 1.0,
    "hiking_area": 3.0,
    "golf_course": 4.5,
}
_DEFAULT_DURATION_HR = 1.0


def _test_mode() -> bool:
    return os.environ.get("TEST_MODE", "false").lower() == "true"


def _require_api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. Real Geocoding/Places/Directions/Weather calls need "
            "a Google Maps Platform API key with those APIs enabled. Set TEST_MODE=true to run "
            "against fixtures instead."
        )
    return key


def _estimate_duration_hr(types: list[str]) -> float:
    for t in types:
        if t in _DURATION_HEURISTIC_HR:
            return _DURATION_HEURISTIC_HR[t]
    return _DEFAULT_DURATION_HR


def geocode(city: str) -> tuple[float, float] | None:
    if _test_mode():
        return fixtures.geocode(city)

    key = _require_api_key()
    response = httpx.get(_GEOCODE_URL, params={"address": city, "key": key}, timeout=_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None
    location = results[0]["geometry"]["location"]
    return location["lat"], location["lng"]


def search_places(city: str, category: str) -> list[dict]:
    if _test_mode():
        return fixtures.search_places(city, category)

    key = _require_api_key()
    query_term = _CATEGORY_QUERY_TERM.get(category, category)
    response = httpx.post(
        _PLACES_SEARCH_URL,
        json={"textQuery": f"{query_term} in {city}"},
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.location,places.types,"
                "places.formattedAddress,places.photos"
            ),
        },
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    places = response.json().get("places") or []

    results = []
    for place in places:
        location = place.get("location") or {}
        photos = place.get("photos") or []
        results.append(
            {
                "id": place["id"],
                "name": place.get("displayName", {}).get("text", "Unknown place"),
                "lat": location.get("latitude"),
                "lng": location.get("longitude"),
                "category": category,
                "duration_hr": _estimate_duration_hr(place.get("types") or []),
                "address": place.get("formattedAddress", ""),
                # Places API New: a photo's `name` (e.g. "places/X/photos/Y") is
                # what get_photo_bytes() needs -- not a direct image URL.
                "photo_reference": photos[0]["name"] if photos else None,
            }
        )
    return results


def get_weather(city: str, lat: float, lng: float, dates: list[str]) -> list[dict]:
    if _test_mode():
        return fixtures.get_weather(city, lat, lng, dates)

    key = _require_api_key()
    response = httpx.get(
        _WEATHER_URL,
        params={"key": key, "location.latitude": lat, "location.longitude": lng, "days": len(dates)},
        timeout=_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    forecast_days = response.json().get("forecastDays") or []

    results = []
    for date, day in zip(dates, forecast_days):
        daytime = day.get("daytimeForecast", {})
        condition = daytime.get("weatherCondition", {}).get("description", {}).get("text", "unknown")
        temp_c = (day.get("maxTemperature") or {}).get("degrees")
        rain_percent = (daytime.get("precipitation") or {}).get("probability", {}).get("percent", 0)
        results.append(
            {
                "date": date,
                "condition": condition,
                "temp_c": temp_c,
                "rain_chance": rain_percent / 100,
                "success": True,
            }
        )
    return results


def get_directions(city: str, stops: list[dict]) -> dict:
    if _test_mode():
        return fixtures.get_directions(city, stops)

    if len(stops) < 2:
        return {"travel_hours": 0.0, "polyline": None}

    key = _require_api_key()
    origin = f"{stops[0]['lat']},{stops[0]['lng']}"
    destination = f"{stops[-1]['lat']},{stops[-1]['lng']}"
    params: dict[str, str] = {"origin": origin, "destination": destination, "mode": "driving", "key": key}
    if len(stops) > 2:
        params["waypoints"] = "|".join(f"{s['lat']},{s['lng']}" for s in stops[1:-1])

    response = httpx.get(_DIRECTIONS_URL, params=params, timeout=_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    routes = response.json().get("routes") or []
    if not routes:
        raise RuntimeError(f"Directions API returned no route between the selected stops in {city}")

    legs = routes[0].get("legs") or []
    total_seconds = sum(leg["duration"]["value"] for leg in legs)
    polyline = (routes[0].get("overview_polyline") or {}).get("points")
    return {"travel_hours": total_seconds / 3600, "polyline": polyline}


def get_photo_bytes(photo_reference: str) -> bytes | None:
    """Fetches the actual image bytes for a photo_reference returned by
    search_places. Returns None if there's no reference to fetch (e.g. a
    place with no photos) rather than raising -- a missing attraction photo
    should never block saving the rest of a trip."""
    if not photo_reference:
        return None
    if _test_mode():
        return fixtures.get_photo_bytes(photo_reference)

    key = _require_api_key()
    response = httpx.get(
        f"{_PLACES_BASE_URL}/{photo_reference}/media",
        params={"key": key, "maxHeightPx": 400},
        timeout=_REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.content
