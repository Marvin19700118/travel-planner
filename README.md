# Travel Planner

A ReAct-pattern AI agent that plans a multi-day trip. See [spec.md](spec.md) for the full product spec and the GitHub issues for the ticket breakdown.

Implemented so far: [#2](https://github.com/Marvin19700118/travel-planner/issues/2) (the core loop, `TEST_MODE` fixtures), [#3](https://github.com/Marvin19700118/travel-planner/issues/3) (real Google API + Gemini integration, behind the same seam), [#4](https://github.com/Marvin19700118/travel-planner/issues/4) (the interactive map), part of [#5](https://github.com/Marvin19700118/travel-planner/issues/5) (shared password + deployment artifacts — see "Deployment" below for what's still deferred to a first real deploy), [#6](https://github.com/Marvin19700118/travel-planner/issues/6) (mobile responsive design + PWA), and [#7](https://github.com/Marvin19700118/travel-planner/issues/7) (auto-saved trips with real photos + an AI cover image, and a saved-trips list page).

**A note for whoever changes `static/style.css`, `static/app.js`, `static/manifest.json`, or the icon files next:** bump `CACHE_NAME` in `static/sw.js`. The service worker caches those files under that name; without a bump, a browser that already installed it keeps serving what it cached before your change, indefinitely. This bit me twice while building #6 — CSS and JS fixes silently didn't take effect in a browser that had already installed the previous version, until I bumped the cache name.

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
| `GEMINI_API_KEY` | optional, only when `TEST_MODE=false` | If unset, Thought/Reflection text falls back to the same deterministic strings used in `TEST_MODE`, and the AI cover image is skipped in favor of a real attraction photo — the app stays fully usable with real place/weather/route data even without this key |
| `GOOGLE_MAPS_JS_API_KEY` | to see the interactive map render | Deliberately a **separate** key from `GOOGLE_MAPS_API_KEY` — this one is exposed to the browser, so it needs Maps JavaScript API enabled and an HTTP-referrer restriction set in Cloud Console before it's safe to use anywhere but local dev. If unset, the map area shows "Map isn't configured on this deployment yet." instead of a broken blank space — the rest of the app works fine without it |
| `SHARED_SECRET` | to require a password before anyone can use the app | Opt-in, same pattern as the others: unset means open access (local dev, existing tests need no changes). Set it before deploying anywhere public — see "Deployment" below |

**Live-verified 2026-07-24** against real credentials, including a full real trip-planning run (Taipei) through the deployed app end to end — see "Deployment" below for the actual live URL and the deploy-specific bugs this surfaced:
- Geocoding, Places API (New) Text Search, and Directions all confirmed working against real data.
- `agent/tools.py`'s `search_places` now caps results to `_MAX_RESULTS_PER_CATEGORY = 5` (via the Places API's `pageSize`) — live-discovered bug: Text Search returns up to 20 results per query by default, and `agent/graph.py`'s trim loop (built and only tested against small fixtures, removes one item per iteration within an 8-iteration ceiling) could never converge against the ~30-40 real candidates 2 preferences produced. Every real run failed with `failed_max_iterations` until this cap was added.
- `weather.googleapis.com` returned `403 PERMISSION_DENIED` / `API_KEY_SERVICE_BLOCKED` on first live test — the Weather API is enabled on the GCP project but wasn't in that specific key's API-restrictions allowlist in Cloud Console. Non-fatal (weather is reference-only and already degrades gracefully — see the Directions-failure handling in `agent/graph.py`'s `act()`), but add Weather API to the key's restrictions to actually see forecasts.
- `agent/llm.py`'s Gemini integration uses the `google-genai` SDK. Both `gemini-2.0-flash` and `gemini-2.0-flash-preview-image-generation` are in fact retired (`404 NOT_FOUND`, "no longer available", despite still appearing in `models.list()`) — swapped to `gemini-3.1-flash-lite` / `gemini-3.1-flash-image` (maintainer's preference for the 3.1 series), both confirmed working end-to-end, including through a real deployed run that produced a real saved trip with real attraction photos and a real AI cover image.
- The map (`static/app.js`) was verified with a placeholder key pre-deploy: the day tabs, marker/polyline plumbing, and script loading all work correctly. Not yet re-verified in-browser against the real, deployed `GOOGLE_MAPS_JS_API_KEY` specifically (only verified via `curl` that the key itself is valid for Maps JavaScript API) — worth a quick visual check. Note `google.maps.Marker` is deprecated upstream in favor of `AdvancedMarkerElement`; left as-is since migrating requires a Map ID from Cloud Console and `Marker` remains fully supported with no discontinuation date announced.

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

**Live-deployed 2026-07-24**: https://city-explorer-acj8x.web.app (password-gated — ask the maintainer, not committed anywhere). GCP project `city-explorer-acj8x`, Cloud Run (`travel-planner-api`, `us-central1`) + Firebase Hosting. Two real deployment bugs were caught and fixed only by actually going through this once with real credentials — both documented below since they'd bite anyone else deploying this fresh. A third real bug — the Places results cap in the "Live-verified" section above — surfaced from the same first deploy but lives in `agent/tools.py` rather than the deployment config.

**Why `firebase.json`'s `public` points at the empty `hosting-public/` directory, not `static/`**: the shared-password gate in `auth.py` is FastAPI middleware — it only runs for requests that actually reach the FastAPI app. The original design pointed `"public"` at `static/` on the theory that the catch-all rewrite (`"source": "**"`) would send everything to Cloud Run anyway. That's wrong: Firebase Hosting's routing priority always serves an uploaded static file over a rewrite, regardless of the rewrite's glob pattern — confirmed live (`curl` showed the real `index.html`/`style.css`/`trips.html` served straight from Hosting's Fastly CDN with `X-Cache: HIT`, completely bypassing Cloud Run and the password gate; only paths with no matching static file, like `/api/trips`, actually hit the rewrite). Pointing `public` at an empty directory means no request ever matches a static file, so 100% of traffic falls through to the rewrite → Cloud Run → `auth.py`. Hosting is now purely a CDN/HTTPS front door; the actual `static/` assets are served by `main.py`'s own `StaticFiles` mount, behind the same auth middleware as everything else.

**Why the auth cookie in `auth.py` is named exactly `__session`, not something more descriptive**: Firebase Hosting's CDN strips every cookie *except* one specially-named `__session` cookie from requests before forwarding them to Cloud Run — [documented behavior](https://firebase.google.com/docs/hosting/manage-cache), not a bug on our end. This only affects GET/HEAD (the cacheable methods Hosting's CDN layer actually touches); POST always bypasses the cache entirely and forwarded cookies fine either way. Live symptom before the fix: logging in worked, `POST /api/plan` worked, but `GET /api/plan/{run_id}/stream` and every other GET endpoint 401'd through the Hosting URL specifically — hitting the Cloud Run URL directly (bypassing Hosting) worked throughout, which is what isolated this to a Hosting-layer header strip rather than an `auth.py` bug. Must stay named `__session` for anything routed through Firebase Hosting to work.

First-deploy steps:

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
    --allow-unauthenticated \
    --set-env-vars TEST_MODE=false,SHARED_SECRET=your-password,GOOGLE_MAPS_JS_API_KEY=your-js-key \
    --set-secrets GOOGLE_MAPS_API_KEY=google-maps-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest

# Then Hosting (firebase.json's serviceId/region must match the gcloud deploy above):
firebase login
firebase use --add          # creates .firebaserc with your project ID
firebase deploy --only hosting
```

**`--allow-unauthenticated` is required**, not optional: Cloud Run gates every request with IAM by default, *before* it ever reaches this app's own `auth.py` password middleware. Without this flag, nobody could reach the app at all — not even with the correct `SHARED_SECRET` — because Cloud Run's own gate would 403 the request first. This app's actual access control is `SHARED_SECRET`; `--allow-unauthenticated` just lets requests through to where that check happens.

**`GOOGLE_MAPS_JS_API_KEY` must be in `--set-env-vars`** — easy to miss since it looks like it belongs with the two Secret Manager keys, but `/api/config` reads it straight from the environment; omitting it silently serves an empty key and the map never renders on the deployed site.

Prefer Secret Manager (`--set-secrets`) over `--set-env-vars` for `GOOGLE_MAPS_API_KEY` and `GEMINI_API_KEY` — they're real credentials. `GOOGLE_MAPS_JS_API_KEY` is the one exception: it's meant to be browser-visible, so a plain env var is fine, but restrict it by HTTP referrer (and ideally by API, to just Maps JavaScript API) to the Hosting domain in Cloud Console before deploying — an unrestricted key in page source can be lifted and used to run up usage on any API it's allowed to call.

**Deferred to this first deploy** (not blocking anything else that's been built):
- `storage.py` is still local-JSONL, not Firestore. Cloud Run's filesystem is ephemeral, so run records won't survive a redeploy or a cold restart until this is swapped. Every caller already goes through `storage.save_run`/`load_run`/`list_runs`, so swapping the implementation to `google-cloud-firestore` is expected to be an isolated change to that one file — it just couldn't be built and verified without a real Firestore instance (no local emulator available either: Firebase CLI needs a Java runtime that also isn't installed here).
- Same story for `trips.py` (saved-trip records) and `image_store.py` (attraction/cover photos) from #7: both are local-filesystem stand-ins for Firestore and Firebase Storage respectively, for the same ephemeral-filesystem reason above. Every caller goes through `trips.save_trip`/`list_trips`/`delete_trip` and `image_store.save_image`/`read_image`/`delete_trip_images`, so each is expected to be an isolated swap once real Firestore/Storage credentials exist.
- The `--max-instances=1` flag above is what actually satisfies "a single run's live-update stream and its background reasoning process always talk to the same instance" (the in-memory `_run_queues` dict in `main.py` doesn't work across multiple instances) — this is a deploy-time flag, not something enforced in code, so it's easy to forget on a future redeploy.

## Tests

```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m mypy agent/ main.py storage.py auth.py image_store.py trips.py --ignore-missing-imports
```

All tests run without any real key: the fixture tests set `TEST_MODE=true`, and the real-API/Gemini tests monkeypatch the HTTP/SDK boundary. The password-gate tests set/unset `SHARED_SECRET` per test; no server or real cookie infrastructure needed.

## Project layout

- `agent/state.py` — `PlannerState`, `TripRequest`, and `RunCache` (the per-run tool-call memo)
- `agent/tools.py` — the single seam: `TEST_MODE` switches every external call between fixtures and a real HTTP implementation
- `agent/fixtures.py` — the four scenario fixtures described above
- `agent/llm.py` — Gemini-backed Thought/Reflection narration, with a deterministic fallback when no key is set (tool *selection* always stays deterministic — see the module docstring)
- `agent/graph.py` — the LangGraph loop (`think` → `act` → `reflect` → route) and the `run_planner()` generator that drives it
- `storage.py` — local JSONL run persistence (**not yet Firestore** — see "Deployment")
- `trips.py` — local JSON persistence for auto-saved completed trips, plus the enrichment step that fetches real attraction photos and the AI cover image (**not yet Firestore** — see "Deployment")
- `image_store.py` — local filesystem storage for attraction/cover photos (**not yet Firebase Storage** — see "Deployment")
- `auth.py` — the shared-password gate (cookie check, login page, login handler)
- `main.py` — FastAPI app: the password middleware, `POST /api/plan`, `GET /api/plan/{run_id}/stream` (SSE), `GET /api/plan/{run_id}/replay`, `GET /api/config`, `GET /api/trips`, `DELETE /api/trips/{trip_id}`, `GET /images/{trip_id}/{filename}`, `POST /login`
- `static/` — the plain HTML/CSS/JS frontend, responsive down to a 375px mobile viewport
- `static/trips.html`, `static/trips.js` — the saved-trips list page (cover image, city, day count, delete)
- `static/manifest.json`, `static/icon-*.png` — PWA manifest and icons (a simple sun mark on coral, matching the visual language)
- `static/sw.js` — service worker caching the static shell only (never API responses); see the `CACHE_NAME` note above
- `Dockerfile`, `.dockerignore` — Cloud Run container build (not yet build-tested — no local Docker)
- `firebase.json` — Hosting config, catch-all rewrite to Cloud Run (see "Deployment" for why)
