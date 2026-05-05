from __future__ import annotations

from dataclasses import dataclass

from maestro.core.logger import EventLogger
from maestro.core.message import OrchestrationEvent, new_correlation_id


@dataclass(slots=True)
class AdHocAgentSpec:
    agent_name: str
    creation_reason: str
    role_spec: str
    tool_scope: str = "read-only"
    ttl: str = "single-issue"


class AdHocFactory:
    def __init__(self, logger: EventLogger, task_id: str) -> None:
        self.logger = logger
        self.task_id = task_id

    def create(self, spec: AdHocAgentSpec) -> None:
        self.logger.log_event(
            OrchestrationEvent(
                task_id=self.task_id,
                correlation_id=new_correlation_id(),
                sender="Maestro",
                receiver=spec.agent_name,
                type="agent_create",
                content={
                    "agent_name": spec.agent_name,
                    "creation_reason": spec.creation_reason,
                    "role_spec": spec.role_spec,
                    "tool_scope": spec.tool_scope,
                    "ttl": spec.ttl,
                },
                confidence=0.8,
            )
        )

    def close(self, spec: AdHocAgentSpec, close_reason: str) -> None:
        self.logger.log_event(
            OrchestrationEvent(
                task_id=self.task_id,
                correlation_id=new_correlation_id(),
                sender=spec.agent_name,
                receiver="Maestro",
                type="agent_close",
                content={"agent_name": spec.agent_name, "close_reason": close_reason},
            )
        )
