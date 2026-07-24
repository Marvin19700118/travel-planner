"""Fixtures feed real frontend code paths (e.g. google.maps.geometry's
decodePath), so their shapes need to be genuinely valid, not just present.
"""

from agent import fixtures

# Google's polyline algorithm format uses ASCII 63-126 for encoded chars.
_VALID_POLYLINE_CHARS = set(chr(c) for c in range(63, 127))


def test_multi_stop_polyline_is_valid_encoded_polyline_charset():
    result = fixtures.get_directions("testville", [{"id": "a"}, {"id": "b"}])
    polyline = result["polyline"]

    assert polyline is not None
    assert polyline, "polyline should not be empty for a multi-stop day"
    assert set(polyline) <= _VALID_POLYLINE_CHARS, (
        f"polyline contains characters outside Google's encoded-polyline alphabet: {polyline!r}"
    )


def test_single_stop_has_no_polyline():
    result = fixtures.get_directions("testville", [{"id": "a"}])
    assert result["polyline"] is None


def test_photo_bytes_are_a_real_decodable_image():
    data = fixtures.get_photo_bytes("places/m1/photos/fixture")
    assert data.startswith(b"\x89PNG"), "fixture photo should be real PNG bytes, not a placeholder string"
