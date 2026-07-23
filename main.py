from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import auth
import storage
from agent.graph import run_planner
from agent.state import TripRequest

app = FastAPI()

_run_queues: dict[str, asyncio.Queue] = {}

FRIENDLY_ERROR_MESSAGE = "Something unexpected happened while planning this trip. Please try again."


@app.middleware("http")
async def require_shared_secret(request: Request, call_next):
    if request.url.path == auth.LOGIN_PATH or auth.is_authorized(request):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return auth.render_login_page()


@app.post(auth.LOGIN_PATH)
async def login(request: Request):
    return await auth.handle_login(request)


class PlanRequest(BaseModel):
    city: str
    start_date: str
    days: int = Field(ge=1)
    preferences: list[str] = Field(min_length=1)


def execute_run(run_id: str, request: PlanRequest, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
    """Runs the planner to completion, pushing every event into `queue` as it
    happens and persisting the full record when done. Runs on a worker thread
    so the event loop stays free for other requests; any exception here is
    caught and turned into a friendly terminal event rather than propagating
    and taking down the run.
    """
    events: list[dict] = []

    def emit(event: dict) -> None:
        events.append(event)
        loop.call_soon_threadsafe(queue.put_nowait, event)

    trip = TripRequest(
        city=request.city, start_date=request.start_date, days=request.days, preferences=request.preferences
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


@app.get("/api/plan/{run_id}/replay")
async def replay_plan(run_id: str) -> dict:
    record = storage.load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return record


@app.get("/api/config")
async def get_config() -> dict:
    """Client-safe config only. GOOGLE_MAPS_JS_API_KEY is deliberately a
    separate key from GOOGLE_MAPS_API_KEY (used server-side for Geocoding/
    Places/Directions/Weather) — this one is meant to be visible in the
    browser and should be restricted by HTTP referrer in the Cloud Console.
    An empty string means the map isn't configured yet; the frontend should
    degrade to a "map unavailable" state rather than trying to load it.
    """
    return {"mapsApiKey": os.environ.get("GOOGLE_MAPS_JS_API_KEY", "")}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
