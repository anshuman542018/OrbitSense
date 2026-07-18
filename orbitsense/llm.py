"""LLM provider abstraction for the analyst.

Providers are selected by the ORBITSENSE_LLM env var:

    gemini:gemini-2.5-flash      (default — free tier, GEMINI_API_KEY)
    claude:claude-haiku-4-5      (launch tier, ANTHROPIC_API_KEY)
    none                         (deterministic templates, no network)

The `none` provider matters: the pipeline must run end-to-end — CI, tests,
contributors without keys — producing sensible template cards; the LLM only
upgrades narration quality. Swapping providers at launch is a config change.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod

import requests


class LLMProvider(ABC):
    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict:
        """Return the model's JSON-object response as a dict."""


class NoneProvider(LLMProvider):
    """No network, no keys: the analyst falls back to template narration."""

    def complete_json(self, system: str, user: str) -> dict:
        raise LLMUnavailable("provider 'none' configured")


class LLMUnavailable(Exception):
    pass


class GeminiProvider(LLMProvider):
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        self.key = os.environ.get("GEMINI_API_KEY", "")

    def complete_json(self, system: str, user: str) -> dict:
        if not self.key:
            raise LLMUnavailable("GEMINI_API_KEY not set")
        resp = requests.post(
            self.URL.format(model=self.model),
            params={"key": self.key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)


class ClaudeProvider(LLMProvider):
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str = "claude-haiku-4-5"):
        self.model = model
        self.key = os.environ.get("ANTHROPIC_API_KEY", "")

    def complete_json(self, system: str, user: str) -> dict:
        if not self.key:
            raise LLMUnavailable("ANTHROPIC_API_KEY not set")
        resp = requests.post(
            self.URL,
            headers={
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        # Tolerate models that wrap JSON in a code fence.
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].removeprefix("json").strip()
        return json.loads(text)


def get_provider(spec: str | None = None) -> LLMProvider:
    spec = spec or os.environ.get("ORBITSENSE_LLM", "gemini:gemini-2.5-flash")
    name, _, model = spec.partition(":")
    if name == "none":
        return NoneProvider()
    if name == "gemini":
        return GeminiProvider(model or "gemini-2.5-flash")
    if name == "claude":
        return ClaudeProvider(model or "claude-haiku-4-5")
    raise ValueError(f"unknown LLM provider: {spec!r}")
