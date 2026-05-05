from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str


class LLMProvider(Protocol):
    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        ...
