from __future__ import annotations

from typing import Literal, TypedDict

Status = Literal["in_progress", "done", "infeasible", "no_results", "failed_max_iterations"]


class PlannerState(TypedDict):
    city: str
    start_date: str
    days: int
    preferences: list[str]

    lat: float | None
    lng: float | None
    candidates: dict[str, list[dict]]
    no_results_categories: list[str]

    iteration: int
    max_iterations: int
    consecutive_no_improvement: int
    trim_attempts: int

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


def new_state(city: str, start_date: str, days: int, preferences: list[str]) -> PlannerState:
    return PlannerState(
        city=city,
        start_date=start_date,
        days=days,
        preferences=list(preferences),
        lat=None,
        lng=None,
        candidates={},
        no_results_categories=[],
        iteration=0,
        max_iterations=8,
        consecutive_no_improvement=0,
        trim_attempts=0,
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
