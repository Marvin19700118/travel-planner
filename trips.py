"""Local JSON-file persistence for saved (successfully completed) trips --
standing in for Firestore until #5's swap happens. Every caller goes
through save_trip/list_trips/delete_trip, matching storage.py's pattern
for run records.
"""

from __future__ import annotations

import json
from pathlib import Path

import image_store
from agent import llm, tools

TRIPS_DIR = Path(__file__).parent / "run_logs" / "trips"


def save_trip(trip_id: str, record: dict) -> None:
    TRIPS_DIR.mkdir(parents=True, exist_ok=True)
    (TRIPS_DIR / f"{trip_id}.json").write_text(json.dumps(record), encoding="utf-8")


def list_trips() -> list[dict]:
    if not TRIPS_DIR.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(TRIPS_DIR.glob("*.json"))]


def get_trip(trip_id: str) -> dict | None:
    path = TRIPS_DIR / f"{trip_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_trip(trip_id: str) -> bool:
    path = TRIPS_DIR / f"{trip_id}.json"
    if not path.exists():
        return False
    path.unlink()
    image_store.delete_trip_images(trip_id)
    return True


def _fetch_photo_bytes(photo_reference: str | None) -> bytes | None:
    """A single attraction's photo failing to fetch (an expired reference,
    a transient error) must never block saving the rest of the trip."""
    if not photo_reference:
        return None
    try:
        return tools.get_photo_bytes(photo_reference)
    except Exception:
        return None


def save_completed_trip(
    trip_id: str, city: str, days: int, start_date: str, day_allocations: dict, day_polylines: dict, status: str
) -> None:
    """Called once a run has produced a real day allocation, whether or not
    it fully fit the touring budget (maintainer decision, 2026-07-24: a
    best-effort infeasible/failed_max_iterations itinerary is still worth
    seeing on a map and keeping around, not just a done one). status is
    stored honestly rather than rewritten to "done", so callers can still
    tell a best-effort result apart from a fully-fit one. Fetches a real
    photo per attraction and generates (or falls back for) an AI cover
    image -- every image lookup happens here, exactly once; viewing the
    saved trip later never re-triggers one. day_polylines is stored verbatim
    (already computed by the same Directions call the touring-budget check
    made) so the one-page export view (#8) can render a static map per day
    without a new route-calculation call."""
    enriched_allocations: dict[str, list[dict]] = {}
    fallback_cover_bytes: bytes | None = None

    for day, items in day_allocations.items():
        enriched_items = []
        for item in items:
            photo_bytes = _fetch_photo_bytes(item.get("photo_reference"))
            photo_url = image_store.save_image(trip_id, photo_bytes) if photo_bytes else None
            if photo_bytes and fallback_cover_bytes is None:
                fallback_cover_bytes = photo_bytes
            enriched_items.append({**item, "photo_url": photo_url})
        enriched_allocations[day] = enriched_items

    cover_bytes = llm.generate_cover_image(city) or fallback_cover_bytes
    cover_image_url = image_store.save_image(trip_id, cover_bytes) if cover_bytes else None

    save_trip(
        trip_id,
        {
            "trip_id": trip_id,
            "city": city,
            "days": days,
            "start_date": start_date,
            "status": status,
            "cover_image_url": cover_image_url,
            "day_allocations": enriched_allocations,
            "day_polylines": day_polylines,
        },
    )
