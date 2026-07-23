"""Tool boundary. Every external dependency (geocoding, place search,
weather, directions) is called through this module, and this module is the
single seam: TEST_MODE switches every function between fixture data and a
real implementation. Ticket #2 (real Google API integration) fills in the
`else` branches; until then they raise clearly rather than pretending to work.
"""

from __future__ import annotations

import os

from . import fixtures


def _test_mode() -> bool:
    return os.environ.get("TEST_MODE", "false").lower() == "true"


def geocode(city: str) -> tuple[float, float] | None:
    if _test_mode():
        return fixtures.geocode(city)
    raise NotImplementedError("Real Geocoding API integration is not wired up yet")


def search_places(city: str, category: str) -> list[dict]:
    if _test_mode():
        return fixtures.search_places(city, category)
    raise NotImplementedError("Real Places API integration is not wired up yet")


def get_weather(city: str, dates: list[str]) -> list[dict]:
    if _test_mode():
        return fixtures.get_weather(city, dates)
    raise NotImplementedError("Real Weather API integration is not wired up yet")


def get_directions(city: str, stop_ids: list[str]) -> dict:
    if _test_mode():
        return fixtures.get_directions(city, stop_ids)
    raise NotImplementedError("Real Directions API integration is not wired up yet")
