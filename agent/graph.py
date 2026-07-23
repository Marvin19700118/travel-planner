"""The ReAct planning loop: prepare (ungated) -> think -> act -> reflect ->
route -> (loop back to think | one of three finalize nodes -> END).

`think` decides what to do next and writes it to `actions`; `act` is the only
place that calls the tools module; `reflect` writes a self-critique sentence;
`route_after_reflect` is pure logic with no tool/LLM calls. Both `think` and
`reflect` route their text through `llm.narrate_*`, which uses real Gemini
output when GEMINI_API_KEY is set and falls back to the deterministic text
otherwise — see agent/llm.py for why tool *selection* itself never depends
on the LLM being available.
"""

from __future__ import annotations

from typing import Any, Iterator

from langgraph.graph import END, StateGraph

from . import llm, tools
from .state import PlannerState, TripRequest, day_key, new_state

TOURING_HOURS_PER_DAY = 8.0


# ---------------------------------------------------------------------------
# Preparation phase (not counted against max_iterations)
# ---------------------------------------------------------------------------


def prepare(request: TripRequest) -> PlannerState:
    state = new_state(request)
    cache = state["cache"]

    coords = cache.get_or_compute(("geocode", request.city), lambda: tools.geocode(request.city))
    if coords is None:
        state["status"] = "no_results"
        state["final_report"] = f'Couldn\'t find "{request.city}" — please check the city name and try again.'
        return state
    state["lat"], state["lng"] = coords

    candidates: dict[str, list[dict]] = {}
    no_results: list[str] = []
    for pref in request.preferences:
        def _search(city: str = request.city, category: str = pref) -> list[dict]:
            return tools.search_places(city, category)

        found = cache.get_or_compute(("search_places", request.city, pref), _search)
        candidates[pref] = found
        if not found:
            no_results.append(pref)
    state["candidates"] = candidates

    if request.preferences and len(no_results) == len(request.preferences):
        state["status"] = "no_results"
        state["final_report"] = (
            f'Couldn\'t find any places in "{request.city}" matching your selected preferences.'
        )
    return state


# ---------------------------------------------------------------------------
# Helpers shared by think/act/route
# ---------------------------------------------------------------------------


def _flatten_candidates(candidates: dict[str, list[dict]]) -> list[dict]:
    flat: list[dict] = []
    for pref, items in candidates.items():
        for item in items:
            flat.append({**item, "preference": pref})
    return flat


def _initial_allocation(state: PlannerState) -> dict[str, list[dict]]:
    flat = _flatten_candidates(state["candidates"])
    days = state["days"]
    allocation: dict[str, list[dict]] = {day_key(i + 1): [] for i in range(days)}
    for i, item in enumerate(flat):
        allocation[day_key((i % days) + 1)].append(item)
    return allocation


def _compute_day_metrics(state: PlannerState, day_items: list[dict]) -> dict:
    """Returns {"total": hours, "polyline": route geometry or None}. The
    polyline comes straight from the same Directions call used for the
    feasibility check — the map (ticket #4) reuses it rather than asking
    the browser to compute its own route."""
    duration = sum(item["duration_hr"] for item in day_items)
    stop_ids = tuple(item["id"] for item in day_items)
    city = state["city"]

    def _lookup() -> dict:
        return tools.get_directions(city, day_items)

    directions = state["cache"].get_or_compute(("get_directions", city, stop_ids), _lookup)
    return {"total": duration + directions["travel_hours"], "polyline": directions.get("polyline")}


def _preference_counts(day_allocations: dict[str, list[dict]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for items in day_allocations.values():
        for item in items:
            counts[item["preference"]] = counts.get(item["preference"], 0) + 1
    return counts


def _find_trimmable(day_items: list[dict], counts: dict[str, int]) -> dict | None:
    safe = [item for item in day_items if counts.get(item["preference"], 0) > 1]
    if not safe:
        return None
    return max(safe, key=lambda item: item["duration_hr"])


def _all_preferences_covered(state: PlannerState) -> bool:
    counts = _preference_counts(state["day_allocations"])
    return all(counts.get(pref, 0) > 0 for pref in state["preferences"])


def _observe(tool: str, result: object, *, success: bool = True, error: str | None = None) -> dict:
    return {"tool": tool, "result": result, "success": success, "error": error}


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def think(state: PlannerState) -> dict:
    # NOTE: which tool runs next is decided here deterministically regardless
    # of whether an LLM is configured — see agent/llm.py's module docstring
    # for why. `fallback_thought` is both the deterministic text used when no
    # Gemini key is set, and the factual basis Gemini paraphrases when one is.
    iteration = state["iteration"] + 1
    thoughts = list(state["thoughts"])
    actions = list(state["actions"])

    if iteration == 1:
        fallback_thought = "Let's check the weather for this trip before anything else."
        action = {"tool": "get_weather", "input": {}}
    elif iteration == 2:
        fallback_thought = (
            "Now let's lay out a first draft across all the days and see how the travel time adds up."
        )
        action = {"tool": "initial_allocate_and_check", "input": {}}
    else:
        over_time = state["over_time_days"]
        if over_time:
            worst_day = max(over_time, key=lambda d: state["day_totals"].get(d, 0.0))
            counts = _preference_counts(state["day_allocations"])
            candidate = _find_trimmable(state["day_allocations"].get(worst_day, []), counts)
            if candidate:
                fallback_thought = (
                    f'{worst_day} is over budget. Let\'s drop "{candidate["name"]}", '
                    "the least essential remaining stop, and recheck."
                )
            else:
                fallback_thought = (
                    f"{worst_day} is still over budget, but every remaining stop is the only "
                    "representative of its preference — there's nothing safe left to trim."
                )
            action = {"tool": "trim_worst_day", "input": {"day": worst_day}}
        else:
            fallback_thought = (
                "Every day fits, but not every preference is represented yet — "
                "there's nothing further we can safely do."
            )
            action = {"tool": "trim_worst_day", "input": {"day": None}}

    thought = llm.narrate_thought(fallback_thought, fallback=fallback_thought)
    thoughts.append(thought)
    actions.append(action)
    return {"iteration": iteration, "thoughts": thoughts, "actions": actions}


def act(state: PlannerState) -> dict:
    action = state["actions"][-1]
    tool = action["tool"]
    observations = list(state["observations"])
    day_allocations = dict(state["day_allocations"])
    day_totals = dict(state["day_totals"])
    day_polylines = dict(state["day_polylines"])
    over_time_days = list(state["over_time_days"])
    weather_notes = list(state["weather_notes"])
    consecutive_no_improvement = state["consecutive_no_improvement"]

    if tool == "get_weather":
        try:
            # lat/lng are always set by this point: prepare() returns early with
            # status="no_results" when geocoding fails, before the loop ever starts.
            assert state["lat"] is not None and state["lng"] is not None
            lat, lng = state["lat"], state["lng"]
            results = state["cache"].get_or_compute(
                ("get_weather", state["city"], state["start_date"]),
                lambda: tools.get_weather(state["city"], lat, lng, [state["start_date"]]),
            )
            observations.append(_observe(tool, results))
            for r in results:
                weather_notes.append(f"{r['date']}: {r['condition']}, {r['temp_c']}°C")
        except Exception as exc:  # defensive: a tool failure must not crash the run
            observations.append(_observe(tool, None, success=False, error=str(exc)))

    elif tool == "initial_allocate_and_check":
        candidate_allocation = _initial_allocation(state)
        try:
            candidate_metrics = {day: _compute_day_metrics(state, items) for day, items in candidate_allocation.items()}
        except Exception as exc:  # a Directions failure here must not crash the run
            observations.append(_observe(tool, None, success=False, error=str(exc)))
        else:
            day_allocations = candidate_allocation
            day_totals = {day: m["total"] for day, m in candidate_metrics.items()}
            day_polylines = {day: m["polyline"] for day, m in candidate_metrics.items()}
            over_time_days = [d for d, t in day_totals.items() if t > TOURING_HOURS_PER_DAY]
            observations.append(_observe(tool, {"day_totals": day_totals, "over_time_days": over_time_days}))

    elif tool == "trim_worst_day":
        day = action["input"].get("day")
        if day is None:
            observations.append(_observe(tool, {"removed": None}))
        else:
            counts = _preference_counts(day_allocations)
            items = list(day_allocations.get(day, []))
            candidate = _find_trimmable(items, counts)
            before = day_totals.get(day, 0.0)
            if candidate is None:
                consecutive_no_improvement += 1
                observations.append(
                    _observe(tool, {"removed": None, "day": day, "reason": "no safe item to remove"})
                )
            else:
                trimmed_items = [item for item in items if item is not candidate]
                try:
                    metrics = _compute_day_metrics(state, trimmed_items)
                except Exception as exc:  # a Directions failure must not crash the run either
                    consecutive_no_improvement += 1
                    observations.append(_observe(tool, None, success=False, error=str(exc)))
                else:
                    total = metrics["total"]
                    day_allocations[day] = trimmed_items
                    day_totals[day] = total
                    day_polylines[day] = metrics["polyline"]
                    consecutive_no_improvement = 0 if total < before else consecutive_no_improvement + 1
                    observations.append(
                        _observe(tool, {"removed": candidate["name"], "day": day, "new_total": total})
                    )
            over_time_days = [d for d, t in day_totals.items() if t > TOURING_HOURS_PER_DAY]

    return {
        "observations": observations,
        "day_allocations": day_allocations,
        "day_totals": day_totals,
        "day_polylines": day_polylines,
        "over_time_days": over_time_days,
        "weather_notes": weather_notes,
        "consecutive_no_improvement": consecutive_no_improvement,
    }


def reflect(state: PlannerState) -> dict:
    reflections = list(state["reflections"])
    latest = state["observations"][-1] if state["observations"] else None

    if latest is None:
        fallback_reflection = "Nothing to reflect on yet."
    elif latest["tool"] == "get_weather":
        if latest["success"]:
            fallback_reflection = "Weather noted for reference; it won't change the schedule."
        else:
            fallback_reflection = "Couldn't get a forecast (likely outside the supported date range) — skipping it."
    elif latest["tool"] == "initial_allocate_and_check":
        if state["over_time_days"]:
            fallback_reflection = (
                f"Day(s) over budget: {', '.join(state['over_time_days'])}. Still not good enough — need to trim."
            )
        else:
            fallback_reflection = "Every day fits within the touring budget so far."
    else:  # trim_worst_day
        result = latest["result"]
        if result.get("removed"):
            fallback_reflection = (
                f'Removed "{result["removed"]}" from {result["day"]}; new total is '
                f'{result["new_total"]:.1f}h. Better, but let\'s check if it\'s enough.'
            )
        else:
            fallback_reflection = (
                "Couldn't safely remove anything more without dropping a preference entirely. "
                "Still not good enough."
            )

    reflection = llm.narrate_reflection(fallback_reflection, fallback=fallback_reflection)
    reflections.append(reflection)
    return {"reflections": reflections}


def route_after_reflect(state: PlannerState) -> str:
    if not state["over_time_days"] and _all_preferences_covered(state):
        return "finish"
    if state["consecutive_no_improvement"] >= 2 and state["over_time_days"]:
        return "infeasible"
    if state["iteration"] >= state["max_iterations"]:
        return "give_up"
    return "continue"


def finalize_finish(state: PlannerState) -> dict:
    report = "Your itinerary is ready."
    if state["weather_notes"]:
        report += " Weather for reference: " + "; ".join(state["weather_notes"]) + "."
    return {"status": "done", "final_report": report}


def finalize_infeasible(state: PlannerState) -> dict:
    parts = [
        f"{d} is over by {state['day_totals'][d] - TOURING_HOURS_PER_DAY:.1f}h"
        for d in state["over_time_days"]
    ]
    return {
        "status": "infeasible",
        "final_report": "This doesn't fit: " + "; ".join(parts) + ". Try removing a preference or adding a day.",
    }


def finalize_give_up(state: PlannerState) -> dict:
    counts = _preference_counts(state["day_allocations"])
    missing_preferences = [pref for pref in state["preferences"] if counts.get(pref, 0) == 0]
    gaps = []
    if state["over_time_days"]:
        parts = [
            f"{d} still over by {state['day_totals'][d] - TOURING_HOURS_PER_DAY:.1f}h"
            for d in state["over_time_days"]
        ]
        gaps.append("; ".join(parts))
    if missing_preferences:
        gaps.append(f"no stop found yet for: {', '.join(missing_preferences)}")
    gap_text = "; ".join(gaps) if gaps else "still checking whether the current plan fits"
    return {
        "status": "failed_max_iterations",
        "final_report": (
            f"Hit the {state['max_iterations']}-iteration limit before finishing. "
            f"What's still unresolved: {gap_text}."
        ),
    }


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_graph():
    graph = StateGraph(PlannerState)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.add_node("reflect", reflect)
    graph.add_node("finalize_finish", finalize_finish)
    graph.add_node("finalize_infeasible", finalize_infeasible)
    graph.add_node("finalize_give_up", finalize_give_up)

    graph.set_entry_point("think")
    graph.add_edge("think", "act")
    graph.add_edge("act", "reflect")
    graph.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {
            "continue": "think",
            "finish": "finalize_finish",
            "infeasible": "finalize_infeasible",
            "give_up": "finalize_give_up",
        },
    )
    graph.add_edge("finalize_finish", END)
    graph.add_edge("finalize_infeasible", END)
    graph.add_edge("finalize_give_up", END)
    return graph.compile()


_EVENT_TYPES = {"think": "thought", "reflect": "reflection"}


def run_planner(request: TripRequest) -> Iterator[dict]:
    """Yields one event dict per step. The last event is always type "final".

    Attraction search happens inside `prepare()`, before this generator's
    first event — deliberately not one of the 8 counted iterations, so
    selecting many preferences can't eat the whole reasoning budget just
    gathering candidates. The "preparing" event below exists so the live
    view still shows activity during that phase rather than sitting blank.
    """
    yield {"type": "status", "content": {"status": "preparing"}}
    state = prepare(request)

    if state["status"] == "no_results":
        yield {"type": "status", "content": {"status": "no_results"}}
        yield {"type": "final", "content": {"final_report": state["final_report"], "status": "no_results"}}
        return

    graph = build_graph()
    current: dict[str, Any] = dict(state)
    for update in graph.stream(state, stream_mode="updates", config={"recursion_limit": 100}):
        for node_name, partial in update.items():
            current.update(partial)
            if node_name in _EVENT_TYPES:
                key = "thoughts" if node_name == "think" else "reflections"
                yield {
                    "type": _EVENT_TYPES[node_name],
                    "content": {"iteration": current["iteration"], "text": current[key][-1]},
                }
            elif node_name == "act":
                yield {
                    "type": "action",
                    "content": {"iteration": current["iteration"], "action": current["actions"][-1]},
                }
                yield {
                    "type": "observation",
                    "content": {"iteration": current["iteration"], "observation": current["observations"][-1]},
                }
            elif node_name.startswith("finalize_"):
                yield {"type": "status", "content": {"status": current["status"]}}
                yield {
                    "type": "final",
                    "content": {
                        "final_report": current["final_report"],
                        "status": current["status"],
                        "day_allocations": current.get("day_allocations"),
                        "day_totals": current.get("day_totals"),
                        "day_polylines": current.get("day_polylines"),
                        "iteration": current["iteration"],
                    },
                }
