"""Local file-based persistence for run records (ticket #2 scope). A later
ticket swaps this out for Firestore; callers only depend on save_run /
load_run / list_runs, so that swap shouldn't need to touch main.py or graph.py.
"""

from __future__ import annotations

import json
from pathlib import Path

RUN_LOG_DIR = Path(__file__).parent / "run_logs"


def save_run(run_id: str, request: dict, events: list[dict]) -> None:
    RUN_LOG_DIR.mkdir(exist_ok=True)
    path = RUN_LOG_DIR / f"{run_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": run_id, "request": request}) + "\n")
        for event in events:
            f.write(json.dumps(event) + "\n")


def load_run(run_id: str) -> dict | None:
    path = RUN_LOG_DIR / f"{run_id}.jsonl"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:]]
    return {"run_id": header["run_id"], "request": header["request"], "events": events}


def list_runs() -> list[dict]:
    if not RUN_LOG_DIR.exists():
        return []
    runs = []
    for path in sorted(RUN_LOG_DIR.glob("*.jsonl")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue
        header = json.loads(lines[0])
        events = [json.loads(line) for line in lines[1:]]
        final_events = [e for e in events if e.get("type") == "final"]
        status = final_events[-1]["content"]["status"] if final_events else "in_progress"
        runs.append({"run_id": header["run_id"], "request": header["request"], "status": status})
    return runs
