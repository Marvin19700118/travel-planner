"""Gemini-backed narration for the Thought and Reflection steps.

Scoping note (this could not be verified against a live key while building
it — treat as needing a first real smoke test once GEMINI_API_KEY is set):

Tool/action *selection* — which of get_weather / initial_allocate_and_check
/ trim_worst_day runs next, which day gets trimmed, which stop is safe to
remove — stays fully deterministic in graph.py regardless of whether an LLM
is configured. That logic is what the touring-budget and preference-
coverage acceptance criteria depend on, and there was no live key available
to verify an LLM would reproduce it reliably through function-calling.

What Gemini adds here, when GEMINI_API_KEY is set, is genuine LLM-authored
narration of the already-decided action and its result — the Thought/
Reflection text a user reads is real model output, not a template. Without
a key (including right now, before real credentials are configured), both
functions fall back to the deterministic strings already built and tested
in ticket #2, so the app stays fully usable with real Places/Directions/
Weather data even before Gemini is wired up.
"""

from __future__ import annotations

import os

_MODEL = "gemini-2.0-flash"


def is_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _generate(prompt: str) -> str | None:
    from google import genai  # imported lazily: only needed when a key is actually set

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model=_MODEL, contents=prompt)
    text = (response.text or "").strip()
    return text or None


def _narrate(prompt: str, fallback: str) -> str:
    """Shared by narrate_thought/narrate_reflection: no key, no response, or
    any failure at all falls back — narration is a presentation detail,
    never worth failing a run over."""
    if not is_available():
        return fallback
    try:
        return _generate(prompt) or fallback
    except Exception:
        return fallback


def narrate_thought(context: str, fallback: str) -> str:
    """Returns Gemini's one-sentence narration of what the agent is about to
    do, or `fallback` if no key is configured or the call fails for any reason."""
    return _narrate(
        "You are a trip-planning agent narrating your own next step in one short, "
        "friendly sentence, present tense, first person plural (e.g. \"Let's...\"). "
        f"What's about to happen: {context}\n"
        "Reply with exactly one sentence, no preamble.",
        fallback,
    )


def narrate_reflection(context: str, fallback: str) -> str:
    """Returns Gemini's one-sentence self-critique of what just happened, or
    `fallback` under the same conditions as narrate_thought."""
    return _narrate(
        "You are a trip-planning agent giving a one-sentence, honest self-critique of "
        "what just happened, casual tone. "
        f"What just happened: {context}\n"
        "Reply with exactly one sentence, no preamble.",
        fallback,
    )
