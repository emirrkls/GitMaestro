from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent


class ScribeAgent(BaseAgent):
    name = "Scribe"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue_ref = str(context.get("issue_ref", "unknown"))
        commit_message = f"fix(issue): address {issue_ref} with minimal scoped patch"
        pr_body = "\n".join(
            [
                "## Summary",
                "- Fixes issue with a minimal and reviewed patch.",
                "- Adds validation through orchestration test evidence.",
                "",
                "## Test Plan",
                "- Run discovered test command via Tester.",
                "",
                "## Risk",
                "- Low risk due to constrained scope and critic gate.",
            ]
        )
        return AgentResult(
            summary="Commit message and PR draft prepared.",
            payload={"commit_message": commit_message, "pr_body": pr_body},
            confidence=0.73,
        )
