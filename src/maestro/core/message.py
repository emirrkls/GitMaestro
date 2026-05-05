from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

EventType = Literal[
    "task",
    "result",
    "feedback",
    "escalation",
    "decision",
    "agent_create",
    "agent_close",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class OrchestrationEvent:
    task_id: str
    correlation_id: str
    sender: str
    receiver: str
    type: EventType
    content: dict[str, Any]
    confidence: float | None = None
    blocking_reason: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["confidence"] is not None:
            payload["confidence"] = round(float(payload["confidence"]), 4)
        return payload


def new_correlation_id() -> str:
    return str(uuid4())
