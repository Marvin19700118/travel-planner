# Travel Planner

A ReAct-pattern AI agent that plans a multi-day trip. See [spec.md](spec.md) for the full product spec and the GitHub issues for the ticket breakdown.

This is ticket [#2](https://github.com/Marvin19700118/travel-planner/issues/2): the core Observation → Thought → Action → Reflection loop, running entirely on `TEST_MODE` fixture data (no real external API calls yet — that's ticket #3).

## Setup

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run locally

```bash
.venv\Scripts\python.exe run_dev.py
```

Then open http://127.0.0.1:8000. `run_dev.py` forces `TEST_MODE=true`, since real API integration isn't wired up yet. Try these city names in the form to exercise each terminal state:

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

## Project layout

- `agent/state.py` — the `PlannerState` shape
- `agent/tools.py` — the single seam: `TEST_MODE` switches every external call between fixtures and a real implementation (not yet built)
- `agent/fixtures.py` — the four scenario fixtures described above
- `agent/graph.py` — the LangGraph loop (`think` → `act` → `reflect` → route) and the `run_planner()` generator that drives it
- `storage.py` — local JSONL run persistence (replaced by Firestore in a later ticket)
- `main.py` — FastAPI app: `POST /api/plan`, `GET /api/plan/{run_id}/stream` (SSE), `GET /api/plan/{run_id}/replay`, `GET /api/runs`
- `static/` — the plain HTML/CSS/JS frontend
