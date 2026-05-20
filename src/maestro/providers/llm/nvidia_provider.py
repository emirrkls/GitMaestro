from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from maestro.providers.llm.base import LLMProvider, LLMResponse

_MAX_RETRIES = 5
_INITIAL_BACKOFF = 4.0
_BACKOFF_MULTIPLIER = 2.0
_RETRYABLE_CODES = {429, 500, 502, 503, 504}


class NvidiaProvider(LLMProvider):
    """NVIDIA Build API (OpenAI-compatible chat completions)."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: int = 90,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max(256, int(max_tokens))

    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")

        backoff = _INITIAL_BACKOFF
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            request = urllib.request.Request(
                url=url,
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                payload_out = json.loads(raw or "{}")
                text = _extract_text(payload_out)
                return LLMResponse(text=text, model=model)
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                    detail = body[:1200]
                except OSError:
                    detail = "(no response body)"
                if exc.code in _RETRYABLE_CODES and attempt < _MAX_RETRIES:
                    print(
                        f"[nvidia] {exc.code} on attempt {attempt + 1}/{_MAX_RETRIES + 1}; "
                        f"retrying in {backoff:.0f}s ...",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)
                    backoff *= _BACKOFF_MULTIPLIER
                    last_exc = RuntimeError(f"NVIDIA HTTP error: {exc.code} body={detail}")
                    continue
                raise RuntimeError(f"NVIDIA HTTP error: {exc.code} body={detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < _MAX_RETRIES:
                    print(
                        f"[nvidia] Network error on attempt {attempt + 1}/{_MAX_RETRIES + 1}; "
                        f"retrying in {backoff:.0f}s ...",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)
                    backoff *= _BACKOFF_MULTIPLIER
                    last_exc = RuntimeError(f"NVIDIA network error: {exc.reason}")
                    continue
                raise RuntimeError(f"NVIDIA network error: {exc.reason}") from exc
            except (TimeoutError, OSError) as exc:
                if attempt < _MAX_RETRIES:
                    print(
                        f"[nvidia] Timeout/OS error on attempt {attempt + 1}/{_MAX_RETRIES + 1}; "
                        f"retrying in {backoff:.0f}s ...",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)
                    backoff *= _BACKOFF_MULTIPLIER
                    last_exc = RuntimeError(f"NVIDIA timeout/OS error: {exc}")
                    continue
                raise RuntimeError(f"NVIDIA timeout/OS error: {exc}") from exc

        raise last_exc or RuntimeError("NVIDIA provider: max retries exhausted.")


def _extract_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return "NVIDIA returned no choices."
    first = choices[0]
    if not isinstance(first, dict):
        return "NVIDIA choice format unexpected."
    message = first.get("message", {})
    if not isinstance(message, dict):
        return "NVIDIA message format unexpected."
    return str(message.get("content", ""))
