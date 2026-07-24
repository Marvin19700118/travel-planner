from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, TypedDict

Status = Literal["in_progress", "done", "infeasible", "no_results", "failed_max_iterations"]


@dataclass
class RunCache:
    """A per-run memo for tool calls. Kept in state (not module-level) so a
    cache never leaks between runs — each run gets its own empty cache."""

    _store: dict[tuple, Any] = field(default_factory=dict)

    def get_or_compute(self, key: tuple, compute: Callable[[], Any]) -> Any:
        if key not in self._store:
            self._store[key] = compute()
        return self._store[key]


@dataclass(frozen=True)
class TripRequest:
    """The inputs that describe a trip, bundled so they travel together
    through prepare() / run_planner() instead of as loose parameters.
    `origin` is a free-text address -- every day's route now starts and ends
    there (maintainer decision, 2026-07-24), geocoded the same way `city` is."""

    city: str
    start_date: str
    days: int
    preferences: list[str]
    origin: str


class PlannerState(TypedDict):
    city: str
    origin: str
    start_date: str
    days: int
    preferences: list[str]

    lat: float | None
    lng: float | None
    origin_lat: float | None
    origin_lng: float | None
    candidates: dict[str, list[dict]]
    cache: RunCache

    iteration: int
    max_iterations: int
    consecutive_no_improvement: int

    thoughts: list[str]
    actions: list[dict]
    observations: list[dict]
    reflections: list[str]

    weather_notes: list[str]

    day_allocations: dict[str, list[dict]]
    day_totals: dict[str, float]
    day_polylines: dict[str, str | None]
    # One entry per Directions leg for that day, in route order (origin ->
    # stop 1 -> ... -> stop N -> origin), so a day with N stops has N+1
    # entries. Threaded alongside day_polylines; used only at finalize time
    # to build the 08:00-start clock schedule (agent/graph.py's
    # _build_day_schedule), not consulted by the trim loop itself.
    day_leg_minutes: dict[str, list[float]]
    # Built once, only at finalize time (agent/graph.py's
    # _finalize_enrichment) -- {"day1": {"stops": [{"id", "arrival",
    # "departure"}, ...], "return_time": "HH:MM"}, ...}. Must be a declared
    # field here even though the trim loop never touches it: LangGraph
    # filters each node's returned dict against this TypedDict's keys, so an
    # undeclared key is silently dropped from the state update rather than
    # raising -- confirmed live (the key showed up as null in the final SSE
    # event until this field was added).
    day_schedules: dict[str, dict]
    over_time_days: list[str]

    status: Status
    final_report: str | None


def new_state(request: TripRequest) -> PlannerState:
    return PlannerState(
        city=request.city,
        origin=request.origin,
        start_date=request.start_date,
        days=request.days,
        preferences=list(request.preferences),
        lat=None,
        lng=None,
        origin_lat=None,
        origin_lng=None,
        candidates={},
        cache=RunCache(),
        iteration=0,
        max_iterations=8,
        consecutive_no_improvement=0,
        thoughts=[],
        actions=[],
        observations=[],
        reflections=[],
        weather_notes=[],
        day_allocations={},
        day_totals={},
        day_polylines={},
        day_leg_minutes={},
        day_schedules={},
        over_time_days=[],
        status="in_progress",
        final_report=None,
    )


def day_key(day_number: int) -> str:
    return f"day{day_number}"
