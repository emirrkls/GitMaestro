from __future__ import annotations

import json
import urllib.error
import urllib.request

from maestro.providers.llm.base import LLMProvider, LLMResponse


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, timeout_seconds: int = 45) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 400,
        }
        data = json.dumps(payload).encode("utf-8")
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
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenRouter HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenRouter network error: {exc.reason}") from exc
        payload_out = json.loads(raw or "{}")
        text = _extract_openrouter_text(payload_out)
        return LLMResponse(text=text, model=model)


def _extract_openrouter_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return "OpenRouter returned no choices."
    first = choices[0]
    if not isinstance(first, dict):
        return "OpenRouter choice format unexpected."
    message = first.get("message", {})
    if not isinstance(message, dict):
        return "OpenRouter message format unexpected."
    return str(message.get("content", ""))
