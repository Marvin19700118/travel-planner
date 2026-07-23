import json
import os

os.environ["TEST_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main.storage, "RUN_LOG_DIR", tmp_path / "run_logs")
    with TestClient(main.app) as c:
        yield c


def _collect_sse_events(client: TestClient, run_id: str) -> list[dict]:
    events = []
    with client.stream("GET", f"/api/plan/{run_id}/stream") as response:
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            events.append(json.loads(line[len("data: "):]))
    return events


def test_config_reports_empty_maps_key_when_unset(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_JS_API_KEY", raising=False)
    assert client.get("/api/config").json() == {"mapsApiKey": ""}


def test_config_reports_the_maps_key_when_set(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_JS_API_KEY", "browser-key")
    assert client.get("/api/config").json() == {"mapsApiKey": "browser-key"}


def test_start_plan_returns_a_run_id(client):
    response = client.post(
        "/api/plan",
        json={"city": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    )

    assert response.status_code == 200
    assert "run_id" in response.json()


def test_stream_delivers_events_ending_in_final(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]

    events = _collect_sse_events(client, run_id)

    assert events, "expected at least one SSE event"
    assert events[-1]["type"] == "final"
    assert events[-1]["content"]["status"] == "done"


def test_streaming_an_unknown_run_id_returns_404(client):
    response = client.get("/api/plan/does-not-exist/stream")
    assert response.status_code == 404


def test_replay_returns_the_persisted_record_after_a_run_completes(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "sprawlville", "start_date": "2026-08-01", "days": 1, "preferences": ["hiking", "golf"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)  # drain the stream so the run finishes and persists

    replay = client.get(f"/api/plan/{run_id}/replay")

    assert replay.status_code == 200
    body = replay.json()
    assert body["run_id"] == run_id
    assert body["events"][-1]["type"] == "final"
    assert body["events"][-1]["content"]["status"] == "infeasible"


def test_replay_of_unknown_run_id_returns_404(client):
    response = client.get("/api/plan/does-not-exist/replay")
    assert response.status_code == 404


def test_invalid_request_is_rejected_before_a_run_starts(client):
    response = client.post(
        "/api/plan",
        json={"city": "testville", "start_date": "2026-08-01", "days": 0, "preferences": []},
    )
    assert response.status_code == 422


def test_a_persistent_tool_failure_degrades_to_a_terminal_state_not_a_crash(tmp_path, monkeypatch):
    """A Directions failure is an anticipated tool failure, not a bug — the
    graph itself should absorb it (see agent/graph.py's act()) and reach a
    normal terminal state, rather than falling through to main.py's
    last-resort catch-all."""
    monkeypatch.setattr(main.storage, "RUN_LOG_DIR", tmp_path / "run_logs")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated Directions API failure")

    monkeypatch.setattr("agent.graph.tools.get_directions", boom)

    with TestClient(main.app) as client:
        run_id = client.post(
            "/api/plan",
            json={"city": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
        ).json()["run_id"]

        events = _collect_sse_events(client, run_id)

    assert events[-1]["type"] == "final"
    assert events[-1]["content"]["status"] == "failed_max_iterations"
    assert events[-1]["content"]["final_report"] != main.FRIENDLY_ERROR_MESSAGE
    assert not any(e["type"] == "error" for e in events)


def test_a_truly_unexpected_exception_during_a_run_ends_gracefully_not_with_a_crash(tmp_path, monkeypatch):
    """Simulates a genuine bug in the reasoning logic itself (not an
    anticipated tool failure) to confirm main.py's last-resort catch-all
    still turns it into a friendly terminal event instead of a hung
    connection or an unhandled exception."""
    monkeypatch.setattr(main.storage, "RUN_LOG_DIR", tmp_path / "run_logs")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated bug in the reasoning logic")

    monkeypatch.setattr("agent.graph.think", boom)

    with TestClient(main.app) as client:
        run_id = client.post(
            "/api/plan",
            json={"city": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
        ).json()["run_id"]

        events = _collect_sse_events(client, run_id)

    assert events[-1]["type"] == "final"
    assert events[-1]["content"]["final_report"] == main.FRIENDLY_ERROR_MESSAGE
    assert any(e["type"] == "error" for e in events)
