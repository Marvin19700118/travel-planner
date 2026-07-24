"""Tests for the ReAct planning loop, driven entirely through the
`run_planner` public seam with TEST_MODE fixtures. No internals of think/
act/reflect are touched directly — only the stream of events and the final
outcome, matching the four terminal states from the spec.
"""

import os

os.environ["TEST_MODE"] = "true"

from agent import graph as graph_module  # noqa: E402
from agent import tools as tools_module  # noqa: E402
from agent.graph import DAY_WINDOW_HOURS, _compute_day_metrics, run_planner  # noqa: E402
from agent.state import RunCache, TripRequest  # noqa: E402


def _trip(city: str, days: int, preferences: list[str], origin: str | None = None) -> TripRequest:
    # Origin defaults to the same fixture city -- every scenario city
    # geocodes successfully under TEST_MODE, so this keeps existing tests
    # focused on city-level behavior unless a test cares about origin itself.
    return TripRequest(city=city, start_date="2026-08-01", days=days, preferences=preferences, origin=origin or city)


def _final(events: list[dict]) -> dict:
    assert events, "expected at least one event"
    assert events[-1]["type"] == "final", "the last event must always be the final outcome"
    return events[-1]["content"]


def test_satisfiable_request_reaches_done_within_iteration_cap():
    events = list(run_planner(_trip("testville", 2, ["museum", "food"])))
    final = _final(events)

    assert final["status"] == "done"
    assert final["iteration"] <= 8
    for day, total in final["day_totals"].items():
        assert total <= DAY_WINDOW_HOURS, f"{day} should fit the 12h clock window, got {total}"

    covered = {item["preference"] for items in final["day_allocations"].values() for item in items}
    assert covered == {"museum", "food"}


def test_done_result_carries_a_route_polyline_per_day_for_the_map():
    events = list(run_planner(_trip("testville", 2, ["museum", "food"])))
    final = _final(events)

    assert set(final["day_polylines"]) == set(final["day_allocations"])
    for day in final["day_allocations"]:
        for stop in final["day_allocations"][day]:
            assert "lat" in stop and "lng" in stop and "address" in stop


def test_done_result_carries_a_clock_schedule_anchored_at_08_00_per_day():
    events = list(run_planner(_trip("testville", 2, ["museum", "food"])))
    final = _final(events)

    assert set(final["day_schedules"]) == set(final["day_allocations"])
    for day, items in final["day_allocations"].items():
        schedule = final["day_schedules"][day]
        assert [s["id"] for s in schedule["stops"]] == [item["id"] for item in items]
        for stop_schedule in schedule["stops"]:
            assert stop_schedule["arrival"] < stop_schedule["departure"]
        assert schedule["return_time"] >= schedule["stops"][-1]["departure"]


def test_done_result_attaches_a_description_key_to_every_stop():
    # describe_place() falls back to None with no Gemini key configured
    # (same presentation-detail contract as narrate_thought/reflection) --
    # the key must still be present for the frontend to key off of.
    events = list(run_planner(_trip("testville", 2, ["museum", "food"])))
    final = _final(events)

    for items in final["day_allocations"].values():
        for item in items:
            assert "description" in item


def test_live_events_stream_before_the_final_outcome():
    events = list(run_planner(_trip("testville", 2, ["museum", "food"])))
    kinds = [e["type"] for e in events]

    assert kinds[0] == "status"  # "preparing", emitted before candidate search even starts
    assert kinds.index("thought") < kinds.index("final")
    assert "action" in kinds
    assert "observation" in kinds
    assert "reflection" in kinds
    assert kinds[-1] == "final"
    assert kinds.count("final") == 1


def test_unfittable_preferences_reach_infeasible_with_specific_day_named():
    events = list(run_planner(_trip("sprawlville", 1, ["hiking", "golf"])))
    final = _final(events)

    assert final["status"] == "infeasible"
    assert final["iteration"] <= 8
    assert "day1" in final["final_report"]
    assert "超出" in final["final_report"]


def test_no_matching_places_reaches_no_results():
    events = list(run_planner(_trip("emptyville", 1, ["museum"])))
    final = _final(events)

    assert final["status"] == "no_results"
    assert "emptyville" in final["final_report"]


def test_unrecognized_city_reaches_no_results():
    trip = TripRequest(city="nowhereville", start_date="2026-08-01", days=1, preferences=["museum"], origin="testville")
    events = list(run_planner(trip))
    final = _final(events)

    assert final["status"] == "no_results"
    assert "nowhereville" in final["final_report"]


def test_unrecognized_origin_reaches_no_results_before_the_city_is_even_looked_up():
    # prepare() geocodes origin first (maintainer decision, 2026-07-24), so an
    # unresolvable origin must short-circuit with its own message, never the
    # city's -- even though the city here ("testville") is perfectly valid.
    trip = TripRequest(city="testville", start_date="2026-08-01", days=1, preferences=["museum"], origin="nowhereville")
    events = list(run_planner(trip))
    final = _final(events)

    assert final["status"] == "no_results"
    assert "出發地點" in final["final_report"]
    assert "nowhereville" in final["final_report"]


def test_never_satisfied_plan_stops_at_exactly_the_iteration_cap():
    events = list(run_planner(_trip("loopville", 1, ["food"])))
    final = _final(events)

    assert final["status"] == "failed_max_iterations"
    assert final["iteration"] == 8
    assert "尚未解決" in final["final_report"]

    thought_iterations = [e["content"]["iteration"] for e in events if e["type"] == "thought"]
    assert max(thought_iterations) == 8
    assert len(thought_iterations) == 8


def test_no_results_short_circuits_before_the_main_loop():
    events = list(run_planner(_trip("emptyville", 1, ["museum"])))

    assert not any(e["type"] == "thought" for e in events), (
        "no_results from the preparation phase should never enter the think/act/reflect loop"
    )


def test_done_report_surfaces_weather_reference_note():
    events = list(run_planner(_trip("testville", 2, ["museum", "food"])))
    final = _final(events)

    assert "天氣" in final["final_report"]


def test_give_up_report_names_the_specific_gap():
    events = list(run_planner(_trip("loopville", 1, ["food"])))
    final = _final(events)

    assert "day1" in final["final_report"]
    assert "超出" in final["final_report"]


def test_repeated_directions_lookup_within_a_run_hits_the_tool_once(monkeypatch):
    calls = []
    real_get_directions = tools_module.get_directions

    def counting_get_directions(city, origin, stops):
        calls.append((city, origin, tuple(item["id"] for item in stops)))
        return real_get_directions(city, origin, stops)

    monkeypatch.setattr(graph_module.tools, "get_directions", counting_get_directions)

    state = {"city": "testville", "origin_lat": 10.0, "origin_lng": 20.0, "cache": RunCache()}
    items = [{"id": "f1", "duration_hr": 1.0}, {"id": "f2", "duration_hr": 1.0}]

    first = _compute_day_metrics(state, items)  # type: ignore[arg-type]
    second = _compute_day_metrics(state, items)  # type: ignore[arg-type]

    assert first == second
    assert len(calls) == 1, "the second identical lookup should be served from the run cache"
