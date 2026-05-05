from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from maestro.providers.llm.base import LLMProvider, LLMResponse


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, timeout_seconds: int = 45) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        encoded_key = urllib.parse.quote(self.api_key)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={encoded_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Gemini HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Gemini network error: {exc.reason}") from exc
        payload_out = json.loads(raw or "{}")
        text = _extract_gemini_text(payload_out)
        return LLMResponse(text=text, model=model)


def _extract_gemini_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        return "Gemini returned no candidates."
    first = candidates[0]
    if not isinstance(first, dict):
        return "Gemini candidate format unexpected."
    content = first.get("content", {})
    if not isinstance(content, dict):
        return "Gemini content format unexpected."
    parts = content.get("parts", [])
    if not isinstance(parts, list) or not parts:
        return "Gemini returned empty parts."
    first_part = parts[0]
    if not isinstance(first_part, dict):
        return "Gemini part format unexpected."
    return str(first_part.get("text", ""))
