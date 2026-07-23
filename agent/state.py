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
    """The four inputs that describe a trip, bundled so they travel together
    through prepare() / run_planner() instead of as four loose parameters."""

    city: str
    start_date: str
    days: int
    preferences: list[str]


class PlannerState(TypedDict):
    city: str
    start_date: str
    days: int
    preferences: list[str]

    lat: float | None
    lng: float | None
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
    over_time_days: list[str]

    status: Status
    final_report: str | None


def new_state(request: TripRequest) -> PlannerState:
    return PlannerState(
        city=request.city,
        start_date=request.start_date,
        days=request.days,
        preferences=list(request.preferences),
        lat=None,
        lng=None,
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
        over_time_days=[],
        status="in_progress",
        final_report=None,
    )


def day_key(day_number: int) -> str:
    return f"day{day_number}"
