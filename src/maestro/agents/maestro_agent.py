from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value


class MaestroAgent(BaseAgent):
    name = "Maestro"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        score_complexity = str(context.get("complexity", "unknown"))

        prompt = (
            "You are Maestro orchestrator. Triage the GitHub issue for automated fixing.\n"
            'Return JSON only: {"triage_decision":"proceed" or "needs_clarification", '
            '"risk":"low|medium|high", "rationale":"one paragraph"}\n'
            f"ScoreComplexityHint:{score_complexity}\n\nIssue:\n{issue[:4000]}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        parsed = extract_first_json_value(response.text)

        triage = "proceed"
        risk = "low"
        rationale = response.text[:2000]

        if isinstance(parsed, dict):
            td = parsed.get("triage_decision")
            if isinstance(td, str) and td.strip().lower() in ("proceed", "needs_clarification"):
                triage = td.strip().lower()
            rk = parsed.get("risk")
            if isinstance(rk, str) and rk.strip().lower() in ("low", "medium", "high"):
                risk = rk.strip().lower()
            ra = parsed.get("rationale")
            if isinstance(ra, str) and ra.strip():
                rationale = ra.strip()

        if len(issue.strip()) < 12:
            triage = "needs_clarification"
            rationale = "Issue text too short for safe automation."

        return AgentResult(
            summary="Issue triaged and route selected.",
            payload={
                "triage_decision": triage,
                "complexity_hint": score_complexity,
                "risk": risk,
                "maestro_rationale": rationale,
            },
            confidence=0.82 if triage == "proceed" else 0.55,
        )
