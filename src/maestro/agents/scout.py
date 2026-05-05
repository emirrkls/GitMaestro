from __future__ import annotations

from pathlib import Path

from maestro.agents.base import AgentResult, BaseAgent


class ScoutAgent(BaseAgent):
    name = "Scout"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        repo_path = Path(str(context.get("repo_path", ".")))
        candidate_files = sorted(str(p.relative_to(repo_path)) for p in repo_path.rglob("*.py"))[:8]
        prompt = (
            "Given issue text and candidate files, infer likely impacted areas.\n"
            f"Issue: {issue}\nFiles: {candidate_files}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        return AgentResult(
            summary="Relevant code areas explored.",
            payload={
                "candidate_files": candidate_files,
                "scout_notes": response.text,
            },
            confidence=0.68,
        )
