# Travel Planner

A ReAct-pattern AI agent that plans a multi-day trip. See [spec.md](spec.md) for the full product spec and the GitHub issues for the ticket breakdown.

Implemented so far: [#2](https://github.com/Marvin19700118/travel-planner/issues/2) (the core loop, `TEST_MODE` fixtures), [#3](https://github.com/Marvin19700118/travel-planner/issues/3) (real Google API + Gemini integration, behind the same seam), [#4](https://github.com/Marvin19700118/travel-planner/issues/4) (the interactive map), and part of [#5](https://github.com/Marvin19700118/travel-planner/issues/5) (shared password + deployment artifacts — see "Deployment" below for what's still deferred to a first real deploy).

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
| `GOOGLE_MAPS_JS_API_KEY` | to see the interactive map render | Deliberately a **separate** key from `GOOGLE_MAPS_API_KEY` — this one is exposed to the browser, so it needs Maps JavaScript API enabled and an HTTP-referrer restriction set in Cloud Console before it's safe to use anywhere but local dev. If unset, the map area shows "Map isn't configured on this deployment yet." instead of a broken blank space — the rest of the app works fine without it |
| `SHARED_SECRET` | to require a password before anyone can use the app | Opt-in, same pattern as the others: unset means open access (local dev, existing tests need no changes). Set it before deploying anywhere public — see "Deployment" below |

**Not yet verified against a live key** — built and tested against mocked HTTP responses / mocked Gemini calls only, since no real credentials were available while building this. Treat the real-API and Gemini paths as needing a first live smoke test once keys are set:
- `_GEOCODE_URL`, `_PLACES_SEARCH_URL`, `_DIRECTIONS_URL` in `agent/tools.py` use documented, stable Google Maps Platform endpoints and are the lower-risk pieces
- `_WEATHER_URL` in `agent/tools.py` targets Google's newer Weather API — this is the most likely to need adjusting once tested live; a forecast failure here is non-fatal (weather is reference-only) but worth checking first
- `agent/llm.py`'s Gemini integration uses the `google-genai` SDK (`gemini-2.0-flash`) — worth confirming the model name is still current
- The map (`static/app.js`) was verified with a placeholder key: the day tabs, marker/polyline plumbing, and script loading all work correctly (confirmed in-browser — Google's SDK itself reports `InvalidKeyMapError`/`InvalidKey`, nothing from this app's own code). It should just work once a real, referrer-restricted key is set — no code changes expected, only a first visual check. Note `google.maps.Marker` is deprecated upstream in favor of `AdvancedMarkerElement`; left as-is for now since migrating requires a Map ID from Cloud Console (another new setup step) and `Marker` is still fully supported with no discontinuation date announced

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

## Deployment

**Not yet deployed or deploy-tested** — no Docker, Firebase CLI, or `gcloud` credentials were available while building this (deliberately deferred; the maintainer asked to skip anything needing real credentials). `Dockerfile` and `firebase.json` are written and believed correct, but this section is a first-deploy checklist, not a "already verified" report.

**Why `firebase.json` routes every path to Cloud Run** (`"source": "**"`, not just `/api/**`): the shared-password gate in `auth.py` is FastAPI middleware — it only runs for requests that actually reach the FastAPI app. If Firebase Hosting served `static/` directly (the more common Hosting+Cloud Run split), the password gate would never see those requests and the UI would be reachable without a password, failing this ticket's "blocks access to both the UI and the API" requirement. Routing everything to Cloud Run means Hosting is just a CDN/HTTPS front door; the `"public": "static"` directory is required by Firebase but effectively unused since the catch-all rewrite wins first.

First-deploy steps (none of this has been run):

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com
# Enable Geocoding API, Places API (New), Directions API, and Weather API via
# Cloud Console's "APIs & Services" page instead of guessing `gcloud services
# enable` identifiers here -- not confident enough in the exact service names
# (e.g. geocoding-backend.googleapis.com vs geocoding.googleapis.com) to give
# a command that's worth trusting over just clicking "Enable" in the console.

# Build and deploy the API to Cloud Run, pinned to a single instance (see
# ticket #5's acceptance criterion about one instance serving both a run's
# SSE stream and its background reasoning task):
gcloud run deploy travel-planner-api \
    --source . \
    --region us-central1 \
    --max-instances=1 \
    --min-instances=0 \
    --set-env-vars TEST_MODE=false,SHARED_SECRET=your-password \
    --set-secrets GOOGLE_MAPS_API_KEY=google-maps-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest

# Then Hosting (firebase.json's serviceId/region must match the gcloud deploy above):
firebase login
firebase use --add          # creates .firebaserc with your project ID (not committed yet -- doesn't exist)
firebase deploy --only hosting
```

Prefer Secret Manager (`--set-secrets`) over `--set-env-vars` for `GOOGLE_MAPS_API_KEY` and `GEMINI_API_KEY` — they're real credentials. `GOOGLE_MAPS_JS_API_KEY` is the one exception: it's meant to be browser-visible, so a plain env var is fine, but restrict it by HTTP referrer to the Hosting domain in Cloud Console before deploying.

**Deferred to this first deploy** (not blocking anything else that's been built):
- `storage.py` is still local-JSONL, not Firestore. Cloud Run's filesystem is ephemeral, so run records won't survive a redeploy or a cold restart until this is swapped. Every caller already goes through `storage.save_run`/`load_run`/`list_runs`, so swapping the implementation to `google-cloud-firestore` is expected to be an isolated change to that one file — it just couldn't be built and verified without a real Firestore instance (no local emulator available either: Firebase CLI needs a Java runtime that also isn't installed here).
- The `--max-instances=1` flag above is what actually satisfies "a single run's live-update stream and its background reasoning process always talk to the same instance" (the in-memory `_run_queues` dict in `main.py` doesn't work across multiple instances) — this is a deploy-time flag, not something enforced in code, so it's easy to forget on a future redeploy.

## Tests

```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m mypy agent/ main.py storage.py auth.py --ignore-missing-imports
```

All tests run without any real key: the fixture tests set `TEST_MODE=true`, and the real-API/Gemini tests monkeypatch the HTTP/SDK boundary. The password-gate tests set/unset `SHARED_SECRET` per test; no server or real cookie infrastructure needed.

## Project layout

- `agent/state.py` — `PlannerState`, `TripRequest`, and `RunCache` (the per-run tool-call memo)
- `agent/tools.py` — the single seam: `TEST_MODE` switches every external call between fixtures and a real HTTP implementation
- `agent/fixtures.py` — the four scenario fixtures described above
- `agent/llm.py` — Gemini-backed Thought/Reflection narration, with a deterministic fallback when no key is set (tool *selection* always stays deterministic — see the module docstring)
- `agent/graph.py` — the LangGraph loop (`think` → `act` → `reflect` → route) and the `run_planner()` generator that drives it
- `storage.py` — local JSONL run persistence (**not yet Firestore** — see "Deployment")
- `auth.py` — the shared-password gate (cookie check, login page, login handler)
- `main.py` — FastAPI app: the password middleware, `POST /api/plan`, `GET /api/plan/{run_id}/stream` (SSE), `GET /api/plan/{run_id}/replay`, `GET /api/config`, `POST /login`
- `static/` — the plain HTML/CSS/JS frontend
- `Dockerfile`, `.dockerignore` — Cloud Run container build (not yet build-tested — no local Docker)
- `firebase.json` — Hosting config, catch-all rewrite to Cloud Run (see "Deployment" for why)
