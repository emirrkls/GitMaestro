from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent


class SurgeonAgent(BaseAgent):
    name = "Surgeon"

    def run(self, context: dict[str, object]) -> AgentResult:
        retry_count = int(context.get("retry_count", 0))
        issue = str(context.get("issue_text", ""))
        prompt = f"Create a minimal patch for issue: {issue}. retry={retry_count}"
        response = self.llm.complete(model=self.model, prompt=prompt)
        patch = (
            "diff --git a/src/example.py b/src/example.py\n"
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-return old_value\n"
            "+return fixed_value\n"
        )
        return AgentResult(
            summary="Minimal patch prepared.",
            payload={"patch_diff": patch, "surgeon_notes": response.text, "retry_count": retry_count},
            confidence=0.7,
        )
