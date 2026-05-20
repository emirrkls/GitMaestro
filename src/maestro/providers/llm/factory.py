from __future__ import annotations

import os
import sys
import time
from collections import deque
from threading import Lock
from typing import Callable

from maestro.config.settings import RuntimeConfig
from maestro.providers.llm.base import LLMProvider
from maestro.providers.llm.gemini import GeminiProvider
from maestro.providers.llm.mock import MockLLMProvider
from maestro.providers.llm.nvidia_provider import NvidiaProvider
from maestro.providers.llm.ollama_provider import OllamaProvider
from maestro.providers.llm.openrouter import OpenRouterProvider


class RPMRateLimiter:
    def __init__(self, rpm_limit: int) -> None:
        self.rpm_limit = max(0, int(rpm_limit))
        self._hits: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        if self.rpm_limit <= 0:
            return
        while True:
            now = time.time()
            with self._lock:
                cutoff = now - 60.0
                while self._hits and self._hits[0] < cutoff:
                    self._hits.popleft()
                if len(self._hits) < self.rpm_limit:
                    self._hits.append(now)
                    return
                wait_s = max(0.01, 60.0 - (now - self._hits[0]))
            time.sleep(min(wait_s, 1.0))


class RateLimitedProvider(LLMProvider):
    def __init__(
        self,
        inner: LLMProvider,
        *,
        rpm_limit: int,
        provider_name: str,
        model_rpm_overrides: dict[str, int] | None = None,
    ) -> None:
        self.inner = inner
        self.provider_name = provider_name
        self.default_limiter = RPMRateLimiter(rpm_limit)
        self.model_rpm_overrides = {k: max(0, int(v)) for k, v in (model_rpm_overrides or {}).items()}
        self.model_limiters: dict[str, RPMRateLimiter] = {}
        self._lock = Lock()

    def complete(self, *, model: str, prompt: str):
        limiter = self._limiter_for_model(model)
        limiter.acquire()
        return self.inner.complete(model=model, prompt=prompt)

    def _limiter_for_model(self, model: str) -> RPMRateLimiter:
        rpm = self.model_rpm_overrides.get(model)
        if rpm is None:
            return self.default_limiter
        with self._lock:
            limiter = self.model_limiters.get(model)
            if limiter is None:
                limiter = RPMRateLimiter(rpm)
                self.model_limiters[model] = limiter
            return limiter


class PrefixHybridProvider(LLMProvider):
    def __init__(
        self,
        *,
        local: LLMProvider,
        nvidia: LLMProvider | None,
    ) -> None:
        self.local = local
        self.nvidia = nvidia

    def complete(self, *, model: str, prompt: str):
        prefix, resolved = _split_model_prefix(model)
        if prefix in (None, "local", "ollama"):
            return self.local.complete(model=resolved, prompt=prompt)
        if prefix == "nvidia":
            if self.nvidia is None:
                raise RuntimeError(
                    "Model requested NVIDIA provider but NVIDIA_API_KEY/NVCF_API_KEY is not set."
                )
            return self.nvidia.complete(model=resolved, prompt=prompt)
        raise RuntimeError(
            f"Unknown hybrid model prefix '{prefix}' for model='{model}'. "
            "Use local/<model> or nvidia/<model>."
        )


def _split_model_prefix(model: str) -> tuple[str | None, str]:
    head, sep, tail = model.partition("/")
    if sep and head.lower() in {"local", "ollama", "nvidia"}:
        return head.lower(), tail.strip()
    return None, model


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
    if runtime.llm_backend == "hybrid":
        print("[maestro] Using Hybrid backend (local + NVIDIA via model prefixes).", file=sys.stderr)
        local_provider = OllamaProvider(
            base_url=runtime.ollama_base_url,
            timeout_seconds=runtime.ollama_timeout_seconds,
            max_tokens=runtime.ollama_max_tokens,
            think=runtime.ollama_think,
        )
        nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip() or os.getenv("NVCF_API_KEY", "").strip()
        nvidia_provider: LLMProvider | None = None
        if nvidia_key:
            nvidia_raw = NvidiaProvider(
                api_key=nvidia_key,
                base_url=runtime.nvidia_base_url,
                timeout_seconds=runtime.nvidia_timeout_seconds,
                max_tokens=runtime.nvidia_max_tokens,
            )
            nvidia_provider = RateLimitedProvider(
                nvidia_raw,
                rpm_limit=runtime.nvidia_rpm_limit,
                provider_name="nvidia",
                model_rpm_overrides=runtime.nvidia_rpm_overrides,
            )
        else:
            print(
                "[maestro] WARNING: Hybrid backend active but NVIDIA_API_KEY/NVCF_API_KEY missing. "
                "nvidia/* models will fail; local/* models continue.",
                file=sys.stderr,
            )
        return PrefixHybridProvider(local=local_provider, nvidia=nvidia_provider)

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
