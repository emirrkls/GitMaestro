from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent


class AnalystAgent(BaseAgent):
    name = "Analyst"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        prompt = (
            "Decompose this issue, list root-cause hypotheses and concise repro steps:\n"
            f"{issue}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        hypotheses = [
            "Input validation missing",
            "Edge-case state transition not handled",
        ]
        repro_steps = [
            "Open target screen",
            "Trigger issue condition",
            "Observe inconsistent result",
        ]
        return AgentResult(
            summary="Issue decomposed with root-cause hypotheses.",
            payload={
                "analysis": response.text,
                "hypotheses": hypotheses,
                "repro_steps": repro_steps,
            },
            confidence=0.72,
        )
