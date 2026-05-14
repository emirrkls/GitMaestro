from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value


class ScribeAgent(BaseAgent):
    name = "Scribe"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue_ref = str(context.get("issue_ref", "unknown"))
        issue = str(context.get("issue_text", ""))[:2000]
        tests = context.get("test_result", {})
        test_ok = isinstance(tests, dict) and bool(tests.get("passed"))

        prompt = (
            "Write a concise Conventional Commit title and markdown PR body for this fix.\n"
            'Return JSON only: {"commit_message":"...", "pr_body_markdown":"..."}\n'
            "Reference tests explicitly. Keep scope tight.\n\n"
            f"Issue:{issue}\nTesterPassed:{test_ok}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        parsed = extract_first_json_value(response.text)

        commit_message = f"fix(issue): address {issue_ref} with scoped patch"
        pr_body = "\n".join(
            [
                "## Summary",
                "- Minimal patch produced after analyst/scout-guided review.",
                f"- Tester signal: {'pass' if test_ok else 'fail or unknown'}.",
                "",
                "## Test Plan",
                "- Run repository test discovery command recorded by Tester.",
                "",
                "## Risk",
                "- Scoped change; monitor related modules for regressions.",
            ]
        )

        if isinstance(parsed, dict):
            cm = parsed.get("commit_message")
            if isinstance(cm, str) and cm.strip():
                commit_message = cm.strip().splitlines()[0][:120]
            pb = parsed.get("pr_body_markdown") or parsed.get("pr_body")
            if isinstance(pb, str) and pb.strip():
                pr_body = pb.strip()

        return AgentResult(
            summary="Commit message and PR draft prepared.",
            payload={"commit_message": commit_message, "pr_body": pr_body},
            confidence=0.76,
        )
