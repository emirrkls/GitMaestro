from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent


class MaestroAgent(BaseAgent):
    name = "Maestro"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        decision = "needs_clarification" if len(issue.strip()) < 15 else "proceed"
        return AgentResult(
            summary="Issue triaged and route selected.",
            payload={
                "triage_decision": decision,
                "complexity_hint": context.get("complexity", "unknown"),
            },
            confidence=0.8,
        )
