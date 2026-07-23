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

CITIES: dict[str, dict] = {
    "testville": {
        "coords": (10.0, 20.0),
        "travel_hr_per_gap": 0.25,
        "candidates": {
            "museum": [
                {"id": "m1", "name": "Testville Museum", "duration_hr": 1.5, "category": "museum", "lat": 10.01, "lng": 20.01},
            ],
            "food": [
                {"id": "f1", "name": "Testville Cafe", "duration_hr": 1.0, "category": "food", "lat": 10.02, "lng": 20.02},
                {"id": "f2", "name": "Testville Diner", "duration_hr": 1.0, "category": "food", "lat": 10.03, "lng": 20.03},
            ],
        },
    },
    "sprawlville": {
        "coords": (30.0, 40.0),
        "travel_hr_per_gap": 1.0,
        "candidates": {
            "hiking": [
                {"id": "h1", "name": "Sprawlville Trail", "duration_hr": 3.0, "category": "hiking", "lat": 30.5, "lng": 40.0},
            ],
            "golf": [
                {"id": "g1", "name": "Sprawlville Golf Course", "duration_hr": 4.5, "category": "golf", "lat": 30.0, "lng": 40.5},
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


def get_directions(city: str, stops: list[dict]) -> dict:
    entry = CITIES.get(city.strip().lower())
    per_gap = entry["travel_hr_per_gap"] if entry else 0.25
    gaps = max(0, len(stops) - 1)
    return {"travel_hours": gaps * per_gap, "polyline": "fixture-polyline"}
