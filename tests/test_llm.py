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
