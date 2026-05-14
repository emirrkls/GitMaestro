from __future__ import annotations

import os
import sys
import time
from typing import Callable

from maestro.config.settings import RuntimeConfig
from maestro.providers.llm.base import LLMProvider
from maestro.providers.llm.gemini import GeminiProvider
from maestro.providers.llm.mock import MockLLMProvider
from maestro.providers.llm.ollama_provider import OllamaProvider
from maestro.providers.llm.openrouter import OpenRouterProvider


class RoutedLLMProvider(LLMProvider):
    def __init__(
        self,
        gemini: LLMProvider,
        openrouter: LLMProvider,
        fallback: LLMProvider | None = None,
        max_retries: int = 2,
    ) -> None:
        self.gemini = gemini
        self.openrouter = openrouter
        self.fallback = fallback
        self.max_retries = max_retries
        self.telemetry_sink: Callable[[str, dict[str, object]], None] | None = None

    def set_telemetry_sink(self, sink: Callable[[str, dict[str, object]], None]) -> None:
        self.telemetry_sink = sink

    def complete(self, *, model: str, prompt: str):
        lowered = model.lower()
        primary = self.openrouter if ("llama" in lowered or "openrouter" in lowered) else self.gemini
        if self.telemetry_sink is not None:
            self.telemetry_sink(
                "llm_attempt",
                {
                    "model": model,
                    "provider": type(primary).__name__,
                    "max_retries": self.max_retries,
                },
            )
        for attempt in range(self.max_retries + 1):
            try:
                result = primary.complete(model=model, prompt=prompt)
                if attempt > 0 and self.telemetry_sink is not None:
                    self.telemetry_sink(
                        "llm_recovery",
                        {
                            "model": model,
                            "provider": type(primary).__name__,
                            "attempt": attempt + 1,
                        },
                    )
                return result
            except RuntimeError as exc:
                if self.telemetry_sink is not None:
                    self.telemetry_sink(
                        "llm_retry",
                        {
                            "model": model,
                            "provider": type(primary).__name__,
                            "attempt": attempt + 1,
                            "error": str(exc),
                        },
                    )
                if attempt >= self.max_retries:
                    break
                # brief backoff for transient provider failures (503/timeout/rate-limit)
                time.sleep(0.8 * (attempt + 1))
        if self.fallback is not None:
            if self.telemetry_sink is not None:
                self.telemetry_sink(
                    "llm_fallback",
                    {
                        "model": model,
                        "primary_provider": type(primary).__name__,
                        "fallback_provider": type(self.fallback).__name__,
                    },
                )
            return self.fallback.complete(model=model, prompt=prompt)
        raise RuntimeError(f"LLM request failed after retries for model={model}")


def build_llm_provider(runtime: RuntimeConfig) -> LLMProvider:
    if runtime.mock_llm:
        return MockLLMProvider()
    if runtime.llm_backend == "ollama":
        print("[maestro] Using Ollama backend (local, no Gemini/OpenRouter quota).", file=sys.stderr)
        return OllamaProvider(
            base_url=runtime.ollama_base_url,
            timeout_seconds=runtime.ollama_timeout_seconds,
            max_tokens=runtime.ollama_max_tokens,
            think=runtime.ollama_think,
        )

    google_key = os.getenv("GOOGLE_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not google_key or not openrouter_key:
        print(
            "[maestro] WARNING: GOOGLE_API_KEY and OPENROUTER_API_KEY must both be set for cloud backend; "
            "falling back to MockLLMProvider (no real patch). Use runtime.llm_backend: ollama for free local runs.",
            file=sys.stderr,
        )
        return MockLLMProvider()
    return RoutedLLMProvider(
        gemini=GeminiProvider(api_key=google_key),
        openrouter=OpenRouterProvider(api_key=openrouter_key),
        fallback=MockLLMProvider(),
        max_retries=2,
    )
