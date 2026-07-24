"""Local filesystem image store, standing in for Firebase Storage until
#5's Firestore/Storage swap happens (see README's "Deployment" section).
Images are served back out through main.py's authenticated
`/images/{trip_id}/{filename}` route. Every caller goes through this
module's small interface, matching storage.py's existing pattern, so
swapping the implementation later shouldn't need to touch callers.
"""

from __future__ import annotations

import uuid
from pathlib import Path

IMAGE_DIR = Path(__file__).parent / "run_logs" / "images"

_MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg"}


def detect_extension(data: bytes) -> str:
    """Sniffs the real format from magic bytes rather than trusting a
    caller-supplied guess -- Gemini's image generation commonly returns PNG
    while Places Photos returns JPEG, and callers here fetch both."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return "jpg"


def media_type_for(filename: str) -> str:
    return _MEDIA_TYPES.get(Path(filename).suffix.lstrip("."), "application/octet-stream")


def _is_safe_segment(segment: str) -> bool:
    """A bare filename/id with no path separators or `..` -- rejects
    anything that could escape IMAGE_DIR/<trip_id>/ once joined into a
    path (e.g. trip_id=".." reaching run_logs/ directly)."""
    return segment == Path(segment).name and segment not in ("", ".", "..")


def save_image(trip_id: str, data: bytes, extension: str | None = None) -> str:
    """Saves image bytes under this trip's folder and returns the URL path
    the frontend can use directly."""
    trip_dir = IMAGE_DIR / trip_id
    trip_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension or detect_extension(data)}"
    (trip_dir / filename).write_bytes(data)
    return f"/images/{trip_id}/{filename}"


def read_image(trip_id: str, filename: str) -> bytes | None:
    if not (_is_safe_segment(trip_id) and _is_safe_segment(filename)):
        return None
    path = IMAGE_DIR / trip_id / filename
    if not path.is_file():
        return None
    return path.read_bytes()


def delete_trip_images(trip_id: str) -> None:
    if not _is_safe_segment(trip_id):
        return
    trip_dir = IMAGE_DIR / trip_id
    if not trip_dir.is_dir():
        return
    for f in trip_dir.iterdir():
        f.unlink()
    trip_dir.rmdir()
