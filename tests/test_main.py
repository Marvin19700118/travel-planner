import json
import os

os.environ["TEST_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main.storage, "RUN_LOG_DIR", tmp_path / "run_logs")
    monkeypatch.setattr(main.trips, "TRIPS_DIR", tmp_path / "trips")
    monkeypatch.setattr("image_store.IMAGE_DIR", tmp_path / "images")
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


def test_config_reports_empty_keys_when_unset(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_JS_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_STATIC_API_KEY", raising=False)
    assert client.get("/api/config").json() == {"mapsApiKey": "", "staticMapsApiKey": ""}


def test_config_reports_the_maps_keys_when_set(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_JS_API_KEY", "browser-key")
    monkeypatch.setenv("GOOGLE_MAPS_STATIC_API_KEY", "static-key")
    assert client.get("/api/config").json() == {"mapsApiKey": "browser-key", "staticMapsApiKey": "static-key"}


def test_config_keys_are_independent_of_each_other(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_JS_API_KEY", "browser-key")
    monkeypatch.delenv("GOOGLE_MAPS_STATIC_API_KEY", raising=False)
    assert client.get("/api/config").json() == {"mapsApiKey": "browser-key", "staticMapsApiKey": ""}


def test_start_plan_returns_a_run_id(client):
    response = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    )

    assert response.status_code == 200
    assert "run_id" in response.json()


def test_stream_delivers_events_ending_in_final(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
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
        json={"city": "sprawlville", "origin": "sprawlville", "start_date": "2026-08-01", "days": 1, "preferences": ["hiking", "golf"]},
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


def test_get_runs_lists_every_past_run_regardless_of_outcome(client):
    done_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    _collect_sse_events(client, done_id)

    infeasible_id = client.post(
        "/api/plan",
        json={"city": "sprawlville", "origin": "sprawlville", "start_date": "2026-08-01", "days": 1, "preferences": ["hiking", "golf"]},
    ).json()["run_id"]
    _collect_sse_events(client, infeasible_id)

    runs = client.get("/api/runs").json()
    run_ids = {r["run_id"] for r in runs}

    assert run_ids == {done_id, infeasible_id}
    statuses = {r["run_id"]: r["status"] for r in runs}
    assert statuses[done_id] == "done"
    assert statuses[infeasible_id] == "infeasible"


def test_a_successful_run_is_auto_saved_as_a_trip(client):
    import trips as trips_module

    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)

    saved = trips_module.list_trips()

    assert len(saved) == 1
    assert saved[0]["trip_id"] == run_id
    assert saved[0]["city"] == "testville"
    assert saved[0]["status"] == "done"
    assert saved[0]["cover_image_url"] is not None


def test_an_infeasible_run_with_a_day_allocation_is_still_saved_as_a_trip(client):
    """A best-effort itinerary that didn't fit the touring budget is still
    worth seeing on a map and keeping around (maintainer decision,
    2026-07-24) -- the status is stored honestly, not rewritten to "done"."""
    import trips as trips_module

    run_id = client.post(
        "/api/plan",
        json={"city": "sprawlville", "origin": "sprawlville", "start_date": "2026-08-01", "days": 1, "preferences": ["hiking", "golf"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)

    saved = trips_module.list_trips()
    assert len(saved) == 1
    assert saved[0]["trip_id"] == run_id
    assert saved[0]["status"] == "infeasible"
    assert saved[0]["day_allocations"]


def test_a_no_results_run_has_nothing_to_save_and_is_not_saved_as_a_trip(client):
    import trips as trips_module

    run_id = client.post(
        "/api/plan",
        json={"city": "emptyville", "origin": "emptyville", "start_date": "2026-08-01", "days": 1, "preferences": ["museum"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)

    assert trips_module.list_trips() == []


def test_a_saved_trips_attractions_have_a_real_photo_url(client):
    import trips as trips_module

    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)

    saved = trips_module.list_trips()[0]
    all_stops = [stop for items in saved["day_allocations"].values() for stop in items]

    assert all_stops, "expected at least one attraction in the saved trip"
    assert all(stop["photo_url"] is not None for stop in all_stops)


def test_get_trip_endpoint_returns_the_saved_record_including_day_polylines(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    events = _collect_sse_events(client, run_id)
    final_day_polylines = events[-1]["content"]["day_polylines"]
    final_day_schedules = events[-1]["content"]["day_schedules"]

    response = client.get(f"/api/trips/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["trip_id"] == run_id
    assert body["day_polylines"] == final_day_polylines
    assert any(body["day_polylines"].values()), "expected at least one day to have a real polyline"
    assert body["day_schedules"] == final_day_schedules
    assert any(body["day_schedules"].values()), "expected at least one day to have a real clock schedule"


def test_get_trip_endpoint_returns_404_for_unknown_trip(client):
    response = client.get("/api/trips/does-not-exist")
    assert response.status_code == 404


def test_get_trips_endpoint_returns_saved_trips(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)

    response = client.get("/api/trips")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["trip_id"] == run_id


def test_delete_trip_endpoint_removes_it_and_its_images(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)
    cover_url = client.get("/api/trips").json()[0]["cover_image_url"]

    response = client.delete(f"/api/trips/{run_id}")

    assert response.status_code == 200
    assert client.get("/api/trips").json() == []
    assert client.get(cover_url).status_code == 404


def test_delete_unknown_trip_returns_404(client):
    response = client.delete("/api/trips/does-not-exist")
    assert response.status_code == 404


def test_trip_image_endpoint_serves_the_saved_bytes(client):
    run_id = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
    ).json()["run_id"]
    _collect_sse_events(client, run_id)
    cover_url = client.get("/api/trips").json()[0]["cover_image_url"]

    response = client.get(cover_url)

    assert response.status_code == 200
    assert response.content  # real bytes, not empty


def test_unknown_trip_image_returns_404(client):
    response = client.get("/images/does-not-exist/nope.jpg")
    assert response.status_code == 404


def test_trip_image_path_traversal_is_rejected(client, tmp_path):
    outside_file = tmp_path / "secret.txt"
    outside_file.write_bytes(b"top secret run log")

    response = client.get("/images/%2E%2E/secret.txt")

    assert response.status_code == 404


def test_invalid_request_is_rejected_before_a_run_starts(client):
    response = client.post(
        "/api/plan",
        json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 0, "preferences": []},
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
            json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
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
            json={"city": "testville", "origin": "testville", "start_date": "2026-08-01", "days": 2, "preferences": ["museum", "food"]},
        ).json()["run_id"]

        events = _collect_sse_events(client, run_id)

    assert events[-1]["type"] == "final"
    assert events[-1]["content"]["final_report"] == main.FRIENDLY_ERROR_MESSAGE
    assert any(e["type"] == "error" for e in events)
