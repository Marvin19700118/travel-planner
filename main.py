from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import image_store
import storage
import trips
from agent.graph import run_planner
from agent.state import TripRequest

app = FastAPI()

_run_queues: dict[str, asyncio.Queue] = {}

FRIENDLY_ERROR_MESSAGE = "規劃這個行程時發生了意外錯誤，請再試一次。"


@app.middleware("http")
async def require_shared_secret(request: Request, call_next):
    if request.url.path == auth.LOGIN_PATH or auth.is_authorized(request):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return auth.render_login_page()


@app.get(auth.LOGIN_PATH)
async def login_page():
    return auth.render_login_page()


@app.post(auth.LOGIN_PATH)
async def login(request: Request):
    return await auth.handle_login(request)


class PlanRequest(BaseModel):
    city: str
    start_date: str
    days: int = Field(ge=1)
    preferences: list[str] = Field(min_length=1)
    # Free-text address; every day's route now starts and ends there
    # (maintainer decision, 2026-07-24), geocoded the same way city is.
    origin: str = Field(min_length=1)


def execute_run(run_id: str, request: PlanRequest, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
    """Runs the planner to completion, pushing every event into `queue` as it
    happens and persisting the full record when done. Runs on a worker thread
    so the event loop stays free for other requests; any exception here is
    caught and turned into a friendly terminal event rather than propagating
    and taking down the run.
    """
    events: list[dict] = []
    final_content: dict | None = None

    def emit(event: dict) -> None:
        nonlocal final_content
        events.append(event)
        if event["type"] == "final":
            final_content = event["content"]
        loop.call_soon_threadsafe(queue.put_nowait, event)

    trip = TripRequest(
        city=request.city,
        start_date=request.start_date,
        days=request.days,
        preferences=request.preferences,
        origin=request.origin,
    )
    try:
        for event in run_planner(trip):
            emit(event)
    except Exception:
        emit({"type": "error", "content": {"message": FRIENDLY_ERROR_MESSAGE}})
        emit(
            {
                "type": "final",
                "content": {"status": "failed_max_iterations", "final_report": FRIENDLY_ERROR_MESSAGE},
            }
        )
    finally:
        storage.save_run(run_id, request.model_dump(), events)
        # Any run that produced an actual day allocation gets saved to the
        # trips list -- even infeasible/failed_max_iterations ones, since a
        # best-effort itinerary that didn't quite fit the touring budget is
        # still worth seeing on a map and keeping around (maintainer
        # decision, 2026-07-24: the earlier "only done" restriction was too
        # strict). The status is stored honestly, not rewritten to "done".
        # no_results never has a day_allocations to begin with (prepare()
        # returns before the loop starts), so it's naturally excluded here
        # without needing an explicit status check. A failure while saving
        # must never look like the planning run itself failed -- the run
        # already finished and streamed its real result.
        if final_content is not None and final_content.get("day_allocations"):
            try:
                trips.save_completed_trip(
                    run_id,
                    request.city,
                    request.days,
                    request.start_date,
                    final_content["day_allocations"],
                    final_content.get("day_polylines") or {},
                    final_content.get("day_schedules") or {},
                    final_content["status"],
                )
            except Exception:
                pass
        loop.call_soon_threadsafe(queue.put_nowait, None)


@app.post("/api/plan")
async def start_plan(request: PlanRequest) -> dict:
    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _run_queues[run_id] = queue
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, execute_run, run_id, request, queue, loop)
    return {"run_id": run_id}


@app.get("/api/plan/{run_id}/stream")
async def stream_plan(run_id: str) -> StreamingResponse:
    queue = _run_queues.get(run_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")

    async def event_source() -> AsyncIterator[str]:
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            _run_queues.pop(run_id, None)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/api/runs")
async def get_runs() -> list[dict]:
    """Every past run regardless of outcome (ticket #9) -- distinct from
    /api/trips, which only lists successful runs saved as trips (ticket #7)."""
    return storage.list_runs()


@app.get("/api/plan/{run_id}/replay")
async def replay_plan(run_id: str) -> dict:
    record = storage.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return record


@app.get("/api/config")
async def get_config() -> dict:
    """Client-safe config only. GOOGLE_MAPS_JS_API_KEY and
    GOOGLE_MAPS_STATIC_API_KEY are deliberately separate from
    GOOGLE_MAPS_API_KEY (used server-side for Geocoding/Places/Directions/
    Weather) — these are meant to be visible in the browser and should be
    restricted by HTTP referrer in the Cloud Console. They're also
    deliberately separate from *each other*: Maps JavaScript API (the
    interactive map, ticket #4) and Maps Static API (the export page's
    per-day maps, ticket #8) can be restricted to their own key each,
    tighter than one key allowed for both. An empty string means that
    particular map isn't configured yet; the frontend should degrade to a
    "map unavailable" state rather than trying to load it.
    """
    return {
        "mapsApiKey": os.environ.get("GOOGLE_MAPS_JS_API_KEY", ""),
        "staticMapsApiKey": os.environ.get("GOOGLE_MAPS_STATIC_API_KEY", ""),
    }


@app.get("/api/trips")
async def get_trips() -> list[dict]:
    return trips.list_trips()


@app.get("/api/trips/{trip_id}")
async def get_trip(trip_id: str) -> dict:
    trip = trips.get_trip(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Unknown trip_id")
    return trip


@app.delete("/api/trips/{trip_id}")
async def delete_trip(trip_id: str) -> dict:
    if not trips.delete_trip(trip_id):
        raise HTTPException(status_code=404, detail="Unknown trip_id")
    return {"deleted": True}


@app.get("/images/{trip_id}/{filename}")
async def get_trip_image(trip_id: str, filename: str) -> Response:
    data = image_store.read_image(trip_id, filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown image")
    return Response(content=data, media_type=image_store.media_type_for(filename))


app.mount("/", StaticFiles(directory="static", html=True), name="static")
