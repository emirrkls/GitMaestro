from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value


class AnalystAgent(BaseAgent):
    name = "Analyst"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        prompt = (
            "Decompose the issue for an automated fix crew.\n"
            'Return JSON only: {"analysis":"longform notes", "hypotheses":["...", "..."], '
            '"repro_steps":["...", "..."]}\n\n'
            f"Issue:\n{issue[:4000]}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        parsed = extract_first_json_value(response.text)

        hypotheses = [
            "Input validation missing",
            "Numeric domain assumption incorrect",
            "Cross-module contract drift",
        ]
        repro_steps = [
            "Load failing scenario referenced in issue",
            "Compare actual vs expected output",
            "Trace to minimal reproducer",
        ]
        analysis_text = response.text

        if isinstance(parsed, dict):
            at = parsed.get("analysis")
            if isinstance(at, str) and at.strip():
                analysis_text = at.strip()
            hy = parsed.get("hypotheses")
            if isinstance(hy, list) and hy:
                hypotheses = [str(x) for x in hy][:8]
            rs = parsed.get("repro_steps")
            if isinstance(rs, list) and rs:
                repro_steps = [str(x) for x in rs][:12]

        return AgentResult(
            summary="Issue decomposed with hypotheses and repro scaffolding.",
            payload={
                "analysis": analysis_text,
                "hypotheses": hypotheses,
                "repro_steps": repro_steps,
            },
            confidence=0.74 if isinstance(parsed, dict) else 0.68,
        )
