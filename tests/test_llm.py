"""Tests for the Gemini narration wrapper. `_generate` (the one function
that actually touches the google-genai SDK) is monkeypatched throughout —
these verify the fallback contract, not live model output.
"""

import pytest

from agent import llm


def test_is_available_reflects_the_env_var(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.is_available() is False

    monkeypatch.setenv("GEMINI_API_KEY", "key")
    assert llm.is_available() is True


def test_narrate_thought_uses_fallback_when_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.narrate_thought("context", fallback="fallback text") == "fallback text"


def test_narrate_thought_uses_generated_text_when_available(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate", lambda prompt: "Let's check the weather first.")

    assert llm.narrate_thought("about to check weather", fallback="fallback") == "Let's check the weather first."


def test_narrate_thought_falls_back_if_generation_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    def boom(prompt):
        raise RuntimeError("network error")

    monkeypatch.setattr(llm, "_generate", boom)

    assert llm.narrate_thought("context", fallback="fallback text") == "fallback text"


def test_narrate_thought_falls_back_on_empty_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate", lambda prompt: None)

    assert llm.narrate_thought("context", fallback="fallback text") == "fallback text"


def test_narrate_reflection_uses_fallback_when_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.narrate_reflection("context", fallback="fallback text") == "fallback text"


def test_narrate_reflection_uses_generated_text_when_available(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate", lambda prompt: "That trimmed an hour off day1.")

    assert llm.narrate_reflection("trimmed a stop", fallback="fallback") == "That trimmed an hour off day1."


def test_narrate_reflection_falls_back_if_generation_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate", lambda prompt: (_ for _ in ()).throw(RuntimeError("boom")))

    assert llm.narrate_reflection("context", fallback="fallback text") == "fallback text"


def test_generate_cover_image_returns_none_when_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.generate_cover_image("Paris") is None


def test_generate_cover_image_returns_bytes_when_available(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate_image", lambda prompt: b"fake-image-bytes")

    assert llm.generate_cover_image("Paris") == b"fake-image-bytes"


def test_generate_cover_image_prompt_includes_the_city(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    captured = {}

    def fake_generate_image(prompt):
        captured["prompt"] = prompt
        return b"bytes"

    monkeypatch.setattr(llm, "_generate_image", fake_generate_image)
    llm.generate_cover_image("Paris")

    assert "Paris" in captured["prompt"]


def test_generate_cover_image_returns_none_if_generation_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    def boom(prompt):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(llm, "_generate_image", boom)

    assert llm.generate_cover_image("Paris") is None


def test_generate_cover_image_returns_none_if_no_image_part_found(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate_image", lambda prompt: None)

    assert llm.generate_cover_image("Paris") is None


def test_describe_place_returns_none_when_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert llm.describe_place("Louvre", "museum", "Paris") is None


def test_describe_place_returns_generated_text_when_available(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setattr(llm, "_generate", lambda prompt: "羅浮宮是世界知名的博物館。")

    assert llm.describe_place("Louvre", "museum", "Paris") == "羅浮宮是世界知名的博物館。"


def test_describe_place_prompt_includes_the_place_category_and_city(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    captured = {}

    def fake_generate(prompt):
        captured["prompt"] = prompt
        return "description"

    monkeypatch.setattr(llm, "_generate", fake_generate)
    llm.describe_place("Louvre", "museum", "Paris")

    assert "Louvre" in captured["prompt"]
    assert "museum" in captured["prompt"]
    assert "Paris" in captured["prompt"]


def test_describe_place_returns_none_if_generation_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    def boom(prompt):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(llm, "_generate", boom)

    assert llm.describe_place("Louvre", "museum", "Paris") is None
