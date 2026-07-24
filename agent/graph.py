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

# Every day is a round trip from the user's origin, departing 08:00 and
# needing to be back by 20:00 (maintainer decision, 2026-07-24; replaces the
# old, clock-agnostic TOURING_HOURS_PER_DAY=8.0 budget). day_totals stays the
# same "duration + travel" hour figure it always was -- only the threshold
# and its meaning changed, from an abstract touring budget to a real
# 08:00-20:00 window.
DAY_WINDOW_HOURS = 12.0
DAY_START_MINUTES = 8 * 60


# ---------------------------------------------------------------------------
# Preparation phase (not counted against max_iterations)
# ---------------------------------------------------------------------------


def prepare(request: TripRequest) -> PlannerState:
    state = new_state(request)
    cache = state["cache"]

    origin_coords = cache.get_or_compute(("geocode", request.origin), lambda: tools.geocode(request.origin))
    if origin_coords is None:
        state["status"] = "no_results"
        state["final_report"] = f'找不到出發地點「{request.origin}」— 請確認地址後再試一次。'
        return state
    state["origin_lat"], state["origin_lng"] = origin_coords

    coords = cache.get_or_compute(("geocode", request.city), lambda: tools.geocode(request.city))
    if coords is None:
        state["status"] = "no_results"
        state["final_report"] = f'找不到「{request.city}」— 請確認城市名稱後再試一次。'
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
        state["final_report"] = f'在「{request.city}」找不到符合所選偏好的地點。'
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
    """Returns {"total": hours, "polyline": route geometry or None,
    "leg_minutes": per-leg minutes in route order}. Every day is now a round
    trip from the user's origin (maintainer decision, 2026-07-24): origin ->
    stops in order -> origin, so N stops means N+1 legs. The polyline and
    leg_minutes both come from this same Directions call — the map (ticket
    #4) and the clock schedule (_build_day_schedule) both reuse it rather
    than asking the browser or a second call to recompute anything."""
    duration = sum(item["duration_hr"] for item in day_items)
    stop_ids = tuple(item["id"] for item in day_items)
    city = state["city"]
    # origin_lat/lng are always set by this point: prepare() returns early
    # with status="no_results" when origin geocoding fails, before the loop
    # ever starts (same guarantee lat/lng already had for get_weather).
    assert state["origin_lat"] is not None and state["origin_lng"] is not None
    origin = (state["origin_lat"], state["origin_lng"])

    def _lookup() -> dict:
        return tools.get_directions(city, origin, day_items)

    directions = state["cache"].get_or_compute(("get_directions", origin, stop_ids), _lookup)
    return {
        "total": duration + directions["travel_hours"],
        "polyline": directions.get("polyline"),
        "leg_minutes": directions.get("leg_minutes") or [],
    }


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
# Finalize-time enrichment: descriptions + clock schedule
# ---------------------------------------------------------------------------


def _describe_allocations(day_allocations: dict[str, list[dict]], city: str) -> dict[str, list[dict]]:
    """Attaches a Gemini-written 50-100-word description to each final stop
    (maintainer decision, 2026-07-24), once, at finalize time -- never
    during the trim loop, so a run with many candidates only ever pays for
    a description on the stops that actually made the final cut. `None`
    (no key configured, or the call failed) is a valid value the frontend
    is expected to handle by simply not showing a description for that
    stop -- same presentation-detail contract as narrate_thought/reflection."""
    return {
        day: [
            {**item, "description": llm.describe_place(item["name"], item["category"], city)} for item in items
        ]
        for day, items in day_allocations.items()
    }


def _format_clock(minutes_after_midnight: float) -> str:
    total = round(minutes_after_midnight)
    hours, minutes = divmod(total, 60)
    return f"{hours:02d}:{minutes:02d}"


def _build_day_schedule(day_items: list[dict], leg_minutes: list[float]) -> dict:
    """Walks a day's stops from an 08:00 departure using the real per-leg
    Directions minutes (origin -> stop 1 -> ... -> stop N -> origin) to
    produce an arrival/departure clock time per stop and a final
    return-to-origin time. Purely a display computation on top of numbers
    already computed for the feasibility check -- it never changes
    day_totals or over_time_days, just narrates them as a schedule."""
    elapsed = 0.0
    stops = []
    for i, item in enumerate(day_items):
        elapsed += leg_minutes[i] if i < len(leg_minutes) else 0.0
        arrival = elapsed
        elapsed += item["duration_hr"] * 60
        departure = elapsed
        stops.append(
            {
                "id": item["id"],
                "arrival": _format_clock(DAY_START_MINUTES + arrival),
                "departure": _format_clock(DAY_START_MINUTES + departure),
            }
        )
    final_leg = leg_minutes[len(day_items)] if len(leg_minutes) > len(day_items) else 0.0
    elapsed += final_leg
    return {"stops": stops, "return_time": _format_clock(DAY_START_MINUTES + elapsed)}


def _finalize_enrichment(state: PlannerState) -> dict:
    """Shared by all three finalize_* nodes: a best-effort itinerary that
    didn't fully fit is still worth describing and scheduling (maintainer
    decision, 2026-07-24), same as it's still worth showing on a map and
    saving -- so this runs for done/infeasible/failed_max_iterations alike."""
    day_allocations = _describe_allocations(state["day_allocations"], state["city"])
    day_schedules = {
        day: _build_day_schedule(day_allocations[day], state["day_leg_minutes"].get(day) or [])
        for day in day_allocations
    }
    return {"day_allocations": day_allocations, "day_schedules": day_schedules}


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
        fallback_thought = "讓我們先查一下這次行程的天氣。"
        action = {"tool": "get_weather", "input": {}}
    elif iteration == 2:
        fallback_thought = "現在來排出第一版每日行程，看看交通時間加起來如何。"
        action = {"tool": "initial_allocate_and_check", "input": {}}
    else:
        over_time = state["over_time_days"]
        if over_time:
            worst_day = max(over_time, key=lambda d: state["day_totals"].get(d, 0.0))
            counts = _preference_counts(state["day_allocations"])
            candidate = _find_trimmable(state["day_allocations"].get(worst_day, []), counts)
            if candidate:
                fallback_thought = (
                    f'{worst_day} 超出時間預算。讓我們拿掉「{candidate["name"]}」這個最不必要的景點，再重新檢查一次。'
                )
            else:
                fallback_thought = (
                    f"{worst_day} 仍然超出時間預算，但剩下的每個景點都是該偏好類別中唯一的代表 "
                    "—— 已經沒有可以安全移除的項目了。"
                )
            action = {"tool": "trim_worst_day", "input": {"day": worst_day}}
        else:
            fallback_thought = "每天的時間都在預算內，但還沒有涵蓋所有偏好 —— 目前沒有可以再安全調整的空間了。"
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
    day_leg_minutes = dict(state["day_leg_minutes"])
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
                weather_notes.append(f"{r['date']}：{r['condition']}，{r['temp_c']}°C")
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
            day_leg_minutes = {day: m["leg_minutes"] for day, m in candidate_metrics.items()}
            over_time_days = [d for d, t in day_totals.items() if t > DAY_WINDOW_HOURS]
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
                    day_leg_minutes[day] = metrics["leg_minutes"]
                    consecutive_no_improvement = 0 if total < before else consecutive_no_improvement + 1
                    observations.append(
                        _observe(tool, {"removed": candidate["name"], "day": day, "new_total": total})
                    )
            over_time_days = [d for d, t in day_totals.items() if t > DAY_WINDOW_HOURS]

    return {
        "observations": observations,
        "day_allocations": day_allocations,
        "day_totals": day_totals,
        "day_polylines": day_polylines,
        "day_leg_minutes": day_leg_minutes,
        "over_time_days": over_time_days,
        "weather_notes": weather_notes,
        "consecutive_no_improvement": consecutive_no_improvement,
    }


def reflect(state: PlannerState) -> dict:
    reflections = list(state["reflections"])
    latest = state["observations"][-1] if state["observations"] else None

    if latest is None:
        fallback_reflection = "目前還沒有可以檢討的內容。"
    elif latest["tool"] == "get_weather":
        if latest["success"]:
            fallback_reflection = "天氣資訊已記錄供參考，不會影響行程安排。"
        else:
            fallback_reflection = "無法取得天氣預報（可能超出支援的日期範圍）—— 先略過。"
    elif latest["tool"] == "initial_allocate_and_check":
        if state["over_time_days"]:
            fallback_reflection = (
                f"超出預算的天數：{'、'.join(state['over_time_days'])}。還不夠好 —— 需要再刪減。"
            )
        else:
            fallback_reflection = "目前每天的時間都在旅遊預算內。"
    else:  # trim_worst_day
        result = latest["result"]
        if result.get("removed"):
            fallback_reflection = (
                f'已從 {result["day"]} 移除「{result["removed"]}」，新的總時數為 '
                f'{result["new_total"]:.1f} 小時。有進步，但還要再確認是否足夠。'
            )
        else:
            fallback_reflection = "已經無法再安全移除任何項目，否則會完全放棄某個偏好。仍然不夠好。"

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
    report = "你的行程已經準備好了。"
    if state["weather_notes"]:
        report += " 天氣參考資訊：" + "；".join(state["weather_notes"]) + "。"
    return {"status": "done", "final_report": report, **_finalize_enrichment(state)}


def finalize_infeasible(state: PlannerState) -> dict:
    parts = [
        f"{d} 超出 {state['day_totals'][d] - DAY_WINDOW_HOURS:.1f} 小時"
        for d in state["over_time_days"]
    ]
    return {
        "status": "infeasible",
        "final_report": "這個行程安排不下：" + "；".join(parts) + "。試著移除一個偏好或增加一天。",
        **_finalize_enrichment(state),
    }


def finalize_give_up(state: PlannerState) -> dict:
    counts = _preference_counts(state["day_allocations"])
    missing_preferences = [pref for pref in state["preferences"] if counts.get(pref, 0) == 0]
    gaps = []
    if state["over_time_days"]:
        parts = [
            f"{d} 仍超出 {state['day_totals'][d] - DAY_WINDOW_HOURS:.1f} 小時"
            for d in state["over_time_days"]
        ]
        gaps.append("；".join(parts))
    if missing_preferences:
        gaps.append(f"尚未找到符合以下偏好的景點：{'、'.join(missing_preferences)}")
    gap_text = "；".join(gaps) if gaps else "仍在確認目前的行程是否可行"
    return {
        "status": "failed_max_iterations",
        "final_report": (
            f"已達到 {state['max_iterations']} 次嘗試上限但仍未完成規劃。尚未解決的部分：{gap_text}。"
        ),
        **_finalize_enrichment(state),
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
                        "day_schedules": current.get("day_schedules"),
                        "iteration": current["iteration"],
                    },
                }
