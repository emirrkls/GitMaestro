from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent


class CriticAgent(BaseAgent):
    name = "Critic"

    def run(self, context: dict[str, object]) -> AgentResult:
        retry_count = int(context.get("retry_count", 0))
        decision = "reject" if retry_count == 0 else "approve"
        feedback = (
            ["Guard missing around edge-case branch", "Add regression test for empty input"]
            if decision == "reject"
            else ["Patch risk acceptable for current scope"]
        )
        return AgentResult(
            summary=f"Patch review completed with {decision}.",
            payload={
                "decision": decision,
                "confidence": 0.78 if decision == "approve" else 0.74,
                "evidence": [
                    "patch_diff presence",
                    f"retry_count={retry_count}",
                    "analysis and scout context",
                ],
                "feedback": feedback,
            },
            confidence=0.78 if decision == "approve" else 0.74,
        )
