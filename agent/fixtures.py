"""Fixture data for TEST_MODE. Each "city" here is a deterministic scenario
designed to drive the planner to one specific terminal state, so the four
end-to-end paths can be verified without any live network call.

- testville   -> done
- sprawlville -> infeasible (two sole-preference-representative stops that
                 together exceed the touring budget and can't be safely trimmed)
- emptyville  -> no_results (city resolves, every preference returns nothing)
- loopville   -> failed_max_iterations (many small, always-safe-to-trim stops
                 that keep improving each iteration but never converge within
                 the iteration cap)

Unknown city names (not in CITIES) simulate a geocoding failure.
"""

from __future__ import annotations

import base64

# A minimal valid 1x1 transparent PNG -- real bytes, not a placeholder
# string, so code that actually decodes/stores the result (e.g. writing it
# to a file, or a future PIL.Image.open() call) works the same way it would
# against a real photo, just with trivial pixel content.
_FIXTURE_PHOTO_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUAAarVyFEAAAAASUVORK5CYII="
)

CITIES: dict[str, dict] = {
    "testville": {
        "coords": (10.0, 20.0),
        "travel_hr_per_gap": 0.25,
        "candidates": {
            "museum": [
                {"id": "m1", "name": "Testville Museum", "duration_hr": 1.5, "category": "museum", "lat": 10.01, "lng": 20.01, "address": "1 Museum Way, Testville", "photo_reference": "places/m1/photos/fixture"},
            ],
            "food": [
                {"id": "f1", "name": "Testville Cafe", "duration_hr": 1.0, "category": "food", "lat": 10.02, "lng": 20.02, "address": "2 Cafe St, Testville", "photo_reference": "places/f1/photos/fixture"},
                {"id": "f2", "name": "Testville Diner", "duration_hr": 1.0, "category": "food", "lat": 10.03, "lng": 20.03, "address": "3 Diner Ave, Testville", "photo_reference": "places/f2/photos/fixture"},
            ],
        },
    },
    "sprawlville": {
        "coords": (30.0, 40.0),
        # Retuned 2026-07-24 for the new origin-round-trip + 12h clock window
        # (was 1.0): 2 stops now means 3 legs (origin->hiking, hiking->golf,
        # golf->origin), and DAY_WINDOW_HOURS grew from 8 to 12 -- at the old
        # per-gap value this scenario would now fit (10.5h <= 12h) instead of
        # demonstrating "infeasible". 2.0 keeps it clearly over (13.5h).
        "travel_hr_per_gap": 2.0,
        "candidates": {
            "hiking": [
                {"id": "h1", "name": "Sprawlville Trail", "duration_hr": 3.0, "category": "hiking", "lat": 30.5, "lng": 40.0, "address": "Trailhead Rd, Sprawlville"},
            ],
            "golf": [
                {"id": "g1", "name": "Sprawlville Golf Course", "duration_hr": 4.5, "category": "golf", "lat": 30.0, "lng": 40.5, "address": "Fairway Dr, Sprawlville"},
            ],
        },
    },
    "emptyville": {
        "coords": (50.0, 60.0),
        "travel_hr_per_gap": 0.25,
        "candidates": {},
    },
    "loopville": {
        "coords": (70.0, 80.0),
        "travel_hr_per_gap": 0.0,
        "candidates": {
            "food": [
                {
                    "id": f"loop-{i}",
                    "name": f"Loopville Snack Stop {i}",
                    "duration_hr": 1.0,
                    "category": "food",
                    "lat": 70.0 + i * 0.001,
                    "lng": 80.0 + i * 0.001,
                    "address": f"{i} Snack Row, Loopville",
                }
                for i in range(20)
            ],
        },
    },
}


def geocode(city: str) -> tuple[float, float] | None:
    entry = CITIES.get(city.strip().lower())
    return entry["coords"] if entry else None


def search_places(city: str, category: str) -> list[dict]:
    entry = CITIES.get(city.strip().lower())
    if not entry:
        return []
    return list(entry["candidates"].get(category, []))


def get_weather(city: str, lat: float, lng: float, dates: list[str]) -> list[dict]:
    return [
        {"date": d, "condition": "sunny", "temp_c": 28, "rain_chance": 0.1, "success": True}
        for d in dates
    ]


# A real, validly-encoded polyline (Google's own algorithm-format example:
# decodes to (38.5,-120.2), (40.7,-120.95), (43.252,-126.453)) — not the
# fixture city's actual coordinates, but a genuine decodable string, so
# testing the map against real decodePath() doesn't require TEST_MODE=false.
_SAMPLE_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def get_directions(city: str, origin: tuple[float, float], stops: list[dict]) -> dict:
    entry = CITIES.get(city.strip().lower())
    per_gap_hr = entry["travel_hr_per_gap"] if entry else 0.25
    if not stops:
        return {"travel_hours": 0.0, "leg_minutes": [], "polyline": None}
    num_legs = len(stops) + 1  # origin -> stop 1 -> ... -> stop N -> origin
    leg_minutes = [per_gap_hr * 60] * num_legs
    return {"travel_hours": sum(leg_minutes) / 60, "leg_minutes": leg_minutes, "polyline": _SAMPLE_POLYLINE}


def get_photo_bytes(photo_reference: str) -> bytes:
    return _FIXTURE_PHOTO_PNG
