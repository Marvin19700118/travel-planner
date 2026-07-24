"""Tests for the real (non-TEST_MODE) tool implementations. No live network
call and no real API key needed — httpx.get/post are monkeypatched to
return a crafted httpx.Response, so these verify request construction and
response parsing only.
"""

import httpx
import pytest

from agent import tools


@pytest.fixture(autouse=True)
def _real_mode(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "false")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")


def _fake_response(json_body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=json_body, request=httpx.Request("GET", "https://example.test"))


def test_geocode_missing_key_raises_a_clear_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_MAPS_API_KEY"):
        tools.geocode("Paris")


def test_geocode_parses_lat_lng_from_the_first_result(monkeypatch):
    def fake_get(url, params, timeout):
        assert url == tools._GEOCODE_URL
        assert params["address"] == "Paris"
        assert params["key"] == "test-key"
        return _fake_response({"results": [{"geometry": {"location": {"lat": 48.86, "lng": 2.35}}}]})

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    assert tools.geocode("Paris") == (48.86, 2.35)


def test_geocode_returns_none_when_no_results(monkeypatch):
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: _fake_response({"results": []}))
    assert tools.geocode("Nowhere12345") is None


def test_search_places_maps_category_to_a_query_and_estimates_duration(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _fake_response(
            {
                "places": [
                    {
                        "id": "p1",
                        "displayName": {"text": "Louvre Museum"},
                        "location": {"latitude": 48.86, "longitude": 2.34},
                        "types": ["museum", "tourist_attraction"],
                        "formattedAddress": "Rue de Rivoli, 75001 Paris",
                        "photos": [{"name": "places/p1/photos/abc123"}],
                    }
                ]
            }
        )

    monkeypatch.setattr(tools.httpx, "post", fake_post)

    results = tools.search_places("Paris", "museum")

    assert captured["url"] == tools._PLACES_SEARCH_URL
    assert captured["json"]["textQuery"] == "museums in Paris"
    assert captured["json"]["pageSize"] == tools._MAX_RESULTS_PER_CATEGORY
    assert captured["headers"]["X-Goog-Api-Key"] == "test-key"
    assert "places.photos" in captured["headers"]["X-Goog-FieldMask"]
    assert results == [
        {
            "id": "p1",
            "name": "Louvre Museum",
            "lat": 48.86,
            "lng": 2.34,
            "category": "museum",
            "duration_hr": 1.5,
            "address": "Rue de Rivoli, 75001 Paris",
            "photo_reference": "places/p1/photos/abc123",
        }
    ]


def test_search_places_falls_back_to_default_duration_for_unmapped_types(monkeypatch):
    monkeypatch.setattr(
        tools.httpx,
        "post",
        lambda *a, **k: _fake_response(
            {
                "places": [
                    {"id": "p2", "displayName": {"text": "Some Shop"}, "location": {"latitude": 1.0, "longitude": 2.0}, "types": ["store"]}
                ]
            }
        ),
    )

    results = tools.search_places("Paris", "shopping")

    assert results[0]["duration_hr"] == 1.0


def test_search_places_returns_empty_list_when_no_places(monkeypatch):
    monkeypatch.setattr(tools.httpx, "post", lambda *a, **k: _fake_response({"places": []}))
    assert tools.search_places("Nowhere12345", "museum") == []


def test_get_weather_parses_forecast_days(monkeypatch):
    def fake_get(url, params, timeout):
        assert url == tools._WEATHER_URL
        assert params["location.latitude"] == 48.86
        return _fake_response(
            {
                "forecastDays": [
                    {
                        "maxTemperature": {"degrees": 22},
                        "daytimeForecast": {
                            "weatherCondition": {"description": {"text": "Partly cloudy"}},
                            "precipitation": {"probability": {"percent": 30}},
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    results = tools.get_weather("Paris", 48.86, 2.35, ["2026-09-01"])

    assert results == [
        {"date": "2026-09-01", "condition": "Partly cloudy", "temp_c": 22, "rain_chance": 0.3, "success": True}
    ]


def test_get_directions_sums_leg_durations_and_returns_the_polyline(monkeypatch):
    def fake_get(url, params, timeout):
        assert url == tools._DIRECTIONS_URL
        assert params["origin"] == "0.0,0.0"
        assert params["destination"] == "0.0,0.0"
        assert params["waypoints"] == "1.0,1.0|2.0,2.0"
        return _fake_response(
            {
                "routes": [
                    {
                        "legs": [
                            {"duration": {"value": 1800}},
                            {"duration": {"value": 3600}},
                            {"duration": {"value": 900}},
                        ],
                        "overview_polyline": {"points": "encoded-polyline"},
                    }
                ]
            }
        )

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    stops = [{"id": "a", "lat": 1.0, "lng": 1.0}, {"id": "b", "lat": 2.0, "lng": 2.0}]
    result = tools.get_directions("Paris", (0.0, 0.0), stops)

    assert result == {"travel_hours": 1.75, "leg_minutes": [30.0, 60.0, 15.0], "polyline": "encoded-polyline"}


def test_get_directions_with_no_stops_needs_no_call(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("should not call the Directions API for zero stops")

    monkeypatch.setattr(tools.httpx, "get", fail)

    assert tools.get_directions("Paris", (0.0, 0.0), []) == {
        "travel_hours": 0.0,
        "leg_minutes": [],
        "polyline": None,
    }


def test_get_directions_raises_a_clear_error_when_no_route_is_found(monkeypatch):
    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: _fake_response({"routes": []}))
    stops = [{"id": "a", "lat": 1.0, "lng": 1.0}, {"id": "b", "lat": 2.0, "lng": 2.0}]

    with pytest.raises(RuntimeError, match="no route"):
        tools.get_directions("Paris", (0.0, 0.0), stops)


def test_get_photo_bytes_fetches_and_follows_redirects(monkeypatch):
    captured = {}

    def fake_get(url, params, timeout, follow_redirects):
        captured["url"] = url
        captured["params"] = params
        captured["follow_redirects"] = follow_redirects
        return httpx.Response(200, content=b"fake-jpeg-bytes", request=httpx.Request("GET", url))

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    result = tools.get_photo_bytes("places/p1/photos/abc123")

    assert captured["url"] == f"{tools._PLACES_BASE_URL}/places/p1/photos/abc123/media"
    assert captured["params"]["key"] == "test-key"
    assert captured["follow_redirects"] is True
    assert result == b"fake-jpeg-bytes"


def test_get_photo_bytes_returns_none_for_no_reference():
    assert tools.get_photo_bytes("") is None
    assert tools.get_photo_bytes(None) is None
