# Travel Planner

A ReAct-pattern AI agent that plans a multi-day trip. See [spec.md](spec.md) for the full product spec and the GitHub issues for the ticket breakdown.

Implemented so far: [#2](https://github.com/Marvin19700118/travel-planner/issues/2) (the core loop, `TEST_MODE` fixtures) and [#3](https://github.com/Marvin19700118/travel-planner/issues/3) (real Google API + Gemini integration, behind the same seam).

## Setup

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Environment variables

| Variable | Required when | Notes |
|---|---|---|
| `TEST_MODE` | always | `true` runs entirely on fixtures (no network, no keys needed); `false` calls real Google APIs |
| `GOOGLE_MAPS_API_KEY` | `TEST_MODE=false` | Needs Geocoding API, Places API (New), Directions API, and Weather API enabled on the same Google Cloud project |
| `GEMINI_API_KEY` | optional, only when `TEST_MODE=false` | If unset, Thought/Reflection text falls back to the same deterministic strings used in `TEST_MODE` — the app stays fully usable with real place/weather/route data even without this key |

**Not yet verified against a live key** — built and tested against mocked HTTP responses / mocked Gemini calls only, since no real credentials were available while building this. Treat the real-API and Gemini paths as needing a first live smoke test once keys are set:
- `_GEOCODE_URL`, `_PLACES_SEARCH_URL`, `_DIRECTIONS_URL` in `agent/tools.py` use documented, stable Google Maps Platform endpoints and are the lower-risk pieces
- `_WEATHER_URL` in `agent/tools.py` targets Google's newer Weather API — this is the most likely to need adjusting once tested live; a forecast failure here is non-fatal (weather is reference-only) but worth checking first
- `agent/llm.py`'s Gemini integration uses the `google-genai` SDK (`gemini-2.0-flash`) — worth confirming the model name is still current

## Run locally

```bash
.venv\Scripts\python.exe run_dev.py
```

Then open http://127.0.0.1:8000. `run_dev.py` forces `TEST_MODE=true` by default (no keys needed). To try the real-API path once you have keys:

```bash
set TEST_MODE=false
set GOOGLE_MAPS_API_KEY=your-key
set GEMINI_API_KEY=your-key
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

In `TEST_MODE=true`, try these city names in the form to exercise each terminal state:

| City | Preferences to select | Days | Outcome |
|---|---|---|---|
| `testville` | museum, food | 2 | `done` |
| `sprawlville` | hiking, golf | 1 | `infeasible` |
| `emptyville` | anything | 1 | `no_results` |
| `loopville` | food | 1 | `failed_max_iterations` |
| any other name | anything | any | `no_results` (unrecognized city) |

## Tests

```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m mypy agent/ main.py storage.py --ignore-missing-imports
```

All tests run without any real key: the fixture tests set `TEST_MODE=true`, and the real-API/Gemini tests monkeypatch the HTTP/SDK boundary.

## Project layout

- `agent/state.py` — `PlannerState`, `TripRequest`, and `RunCache` (the per-run tool-call memo)
- `agent/tools.py` — the single seam: `TEST_MODE` switches every external call between fixtures and a real HTTP implementation
- `agent/fixtures.py` — the four scenario fixtures described above
- `agent/llm.py` — Gemini-backed Thought/Reflection narration, with a deterministic fallback when no key is set (tool *selection* always stays deterministic — see the module docstring)
- `agent/graph.py` — the LangGraph loop (`think` → `act` → `reflect` → route) and the `run_planner()` generator that drives it
- `storage.py` — local JSONL run persistence (replaced by Firestore in a later ticket)
- `main.py` — FastAPI app: `POST /api/plan`, `GET /api/plan/{run_id}/stream` (SSE), `GET /api/plan/{run_id}/replay`
- `static/` — the plain HTML/CSS/JS frontend
