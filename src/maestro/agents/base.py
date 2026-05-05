from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maestro.providers.llm.base import LLMProvider


@dataclass(slots=True)
class AgentResult:
    summary: str
    payload: dict[str, Any]
    confidence: float | None = None


class BaseAgent:
    name = "BaseAgent"

    def __init__(self, llm: LLMProvider, model: str) -> None:
        self.llm = llm
        self.model = model

    def run(self, context: dict[str, Any]) -> AgentResult:
        raise NotImplementedError
