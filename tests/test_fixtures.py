"""Fixtures feed real frontend code paths (e.g. google.maps.geometry's
decodePath), so their shapes need to be genuinely valid, not just present.
"""

from agent import fixtures

# Google's polyline algorithm format uses ASCII 63-126 for encoded chars.
_VALID_POLYLINE_CHARS = set(chr(c) for c in range(63, 127))

_ORIGIN = (10.0, 20.0)


def test_multi_stop_polyline_is_valid_encoded_polyline_charset():
    result = fixtures.get_directions("testville", _ORIGIN, [{"id": "a"}, {"id": "b"}])
    polyline = result["polyline"]

    assert polyline is not None
    assert polyline, "polyline should not be empty for a multi-stop day"
    assert set(polyline) <= _VALID_POLYLINE_CHARS, (
        f"polyline contains characters outside Google's encoded-polyline alphabet: {polyline!r}"
    )


def test_single_stop_still_has_a_polyline_for_the_origin_round_trip():
    # Every day is now origin -> stop -> origin (maintainer decision,
    # 2026-07-24), so even a single stop has two real legs and a route to draw.
    result = fixtures.get_directions("testville", _ORIGIN, [{"id": "a"}])
    assert result["polyline"] is not None
    assert result["leg_minutes"] == [15.0, 15.0]


def test_no_stops_has_no_polyline_and_no_legs():
    result = fixtures.get_directions("testville", _ORIGIN, [])
    assert result == {"travel_hours": 0.0, "leg_minutes": [], "polyline": None}


def test_leg_minutes_has_one_more_entry_than_stops():
    result = fixtures.get_directions("testville", _ORIGIN, [{"id": "a"}, {"id": "b"}, {"id": "c"}])
    assert len(result["leg_minutes"]) == 4


def test_photo_bytes_are_a_real_decodable_image():
    data = fixtures.get_photo_bytes("places/m1/photos/fixture")
    assert data.startswith(b"\x89PNG"), "fixture photo should be real PNG bytes, not a placeholder string"
