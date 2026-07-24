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


def save_image(trip_id: str, data: bytes, extension: str = "jpg") -> str:
    """Saves image bytes under this trip's folder and returns the URL path
    the frontend can use directly."""
    trip_dir = IMAGE_DIR / trip_id
    trip_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    (trip_dir / filename).write_bytes(data)
    return f"/images/{trip_id}/{filename}"


def read_image(trip_id: str, filename: str) -> bytes | None:
    path = IMAGE_DIR / trip_id / filename
    if not path.is_file():
        return None
    return path.read_bytes()


def delete_trip_images(trip_id: str) -> None:
    trip_dir = IMAGE_DIR / trip_id
    if not trip_dir.is_dir():
        return
    for f in trip_dir.iterdir():
        f.unlink()
    trip_dir.rmdir()
