from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

from maestro.providers.llm.base import LLMProvider, LLMResponse


class OllamaProvider(LLMProvider):
    """OpenAI-compatible Chat Completions (Ollama: /v1/chat/completions). No API key."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 600,
        *,
        max_tokens: int = 8192,
        think: bool | str = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max(256, int(max_tokens))
        self.think: bool | str = think

    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, object] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "stream": False,
            "max_tokens": self.max_tokens,
        }
        think_value = _think_request_value(self.think)
        if think_value is not None:
            payload["think"] = think_value
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
        except TimeoutError as exc:
            raise RuntimeError(
                f"Ollama request timed out after {self.timeout_seconds}s (model load + "
                f"`think` generation can be slow). Raise runtime.ollama_timeout_seconds in config, "
                "preload with `ollama run <model>`, or set ollama_think: false to test."
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(
                f"Ollama socket timed out after {self.timeout_seconds}s. "
                "Increase runtime.ollama_timeout_seconds or warm up the model first."
            ) from exc
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
                detail = body[:1200]
            except OSError:
                detail = "(no response body)"
            raise RuntimeError(f"Ollama HTTP error: {exc.code} body={detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama network error: {exc.reason}") from exc

        payload_out = json.loads(raw or "{}")
        text = _extract_choice_text(payload_out)
        return LLMResponse(text=text, model=model)


def _think_request_value(think: bool | str) -> bool | str | None:
    if think is False:
        return None
    if think is True:
        return True
    if isinstance(think, str):
        s = think.strip().lower()
        if s in ("low", "medium", "high"):
            return s
    return None


def _extract_choice_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return "Ollama returned no choices."
    first = choices[0]
    if not isinstance(first, dict):
        return "Ollama choice format unexpected."
    message = first.get("message", {})
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        for key in ("reasoning", "thinking"):
            alt = message.get(key)
            if isinstance(alt, str) and alt.strip():
                return alt
        return str(content or "")
    return str(first.get("text", ""))
