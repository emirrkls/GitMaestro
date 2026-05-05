from __future__ import annotations

from maestro.providers.llm.base import LLMProvider, LLMResponse


class MockLLMProvider(LLMProvider):
    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        clipped = prompt[:160].replace("\n", " ")
        return LLMResponse(text=f"[mock:{model}] {clipped}", model=model)
