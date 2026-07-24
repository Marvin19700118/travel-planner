"""Gemini-backed narration for the Thought and Reflection steps.

Scoping note:

Tool/action *selection* — which of get_weather / initial_allocate_and_check
/ trim_worst_day runs next, which day gets trimmed, which stop is safe to
remove — stays fully deterministic in graph.py regardless of whether an LLM
is configured. That logic is what the touring-budget and preference-
coverage acceptance criteria depend on; an LLM was never trusted to
reproduce it reliably through function-calling.

What Gemini adds here, when GEMINI_API_KEY is set, is genuine LLM-authored
narration of the already-decided action and its result — the Thought/
Reflection text a user reads is real model output, not a template. Without
a key, both functions fall back to the deterministic strings already built
and tested in ticket #2, so the app stays fully usable with real Places/
Directions/Weather data even without Gemini wired up.
"""

from __future__ import annotations

import os

# gemini-2.0-flash was retired (confirmed live: 404 NOT_FOUND, "no longer
# available") despite still showing up in models.list(). Using the 3.1
# series per the maintainer's preference -- confirmed live with a real key.
_MODEL = "gemini-3.1-flash-lite"

# gemini-2.0-flash-preview-image-generation was likewise retired; confirmed
# live that gemini-3.1-flash-image returns an image part.
_IMAGE_MODEL = "gemini-3.1-flash-image"

# Fixed on purpose: every saved trip's cover should look like it came from
# the same illustrator, not a different style each time (spec.md section 3).
_COVER_STYLE_PROMPT = (
    "A bright, flat-illustration style cover image capturing the feeling of a fun trip to {city}. "
    "Warm, sunny color palette (coral and golden tones), casual and relaxed urban mood, "
    "no text, no watermarks, no logos."
)


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
        "你是一個行程規劃代理人，請用一句簡短、親切的句子敘述你即將採取的下一步，"
        "現在時態、第一人稱複數（例如「我們來...」）。"
        f"即將發生的事：{context}\n"
        "請只回覆一句話，不要有任何開場白，並使用繁體中文回覆。",
        fallback,
    )


def narrate_reflection(context: str, fallback: str) -> str:
    """Returns Gemini's one-sentence self-critique of what just happened, or
    `fallback` under the same conditions as narrate_thought."""
    return _narrate(
        "你是一個行程規劃代理人，請用一句誠實、輕鬆口吻的話，簡短自我檢討剛剛發生的事。"
        f"剛剛發生的事：{context}\n"
        "請只回覆一句話，不要有任何開場白，並使用繁體中文回覆。",
        fallback,
    )


def _generate_image(prompt: str) -> bytes | None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=_IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )
    for part in response.parts or []:
        image = part.as_image()
        if image is not None and image.image_bytes:
            return image.image_bytes
    return None


def generate_cover_image(city: str) -> bytes | None:
    """Returns AI-generated cover image bytes for a saved trip, or None if
    no key is set or generation fails for any reason. Callers (main.py) are
    expected to fall back to a real attraction photo when this returns
    None, so a trip is never left without *some* cover image."""
    if not is_available():
        return None
    try:
        return _generate_image(_COVER_STYLE_PROMPT.format(city=city))
    except Exception:
        return None
