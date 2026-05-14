from __future__ import annotations

import re
from pathlib import Path

from maestro.agents.base import AgentResult, BaseAgent


def _keyword_set(issue: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", issue.lower())
    stop = {"the", "and", "for", "that", "with", "this", "from", "have", "has", "into", "issue"}
    return {t for t in tokens if t not in stop}


def _rank_py_files(repo_path: Path, issue: str, limit: int) -> list[str]:
    keywords = _keyword_set(issue)
    scored: list[tuple[int, str]] = []
    for path in repo_path.rglob("*.py"):
        rel = str(path.relative_to(repo_path)).replace("\\", "/")
        blob = f"{rel} {path.stem.lower()}"
        score = sum(1 for k in keywords if k in blob.lower())
        try:
            size_penalty = 0 if path.stat().st_size < 200_000 else -1
        except OSError:
            size_penalty = -1
        scored.append((score + size_penalty, rel))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored:
        return []
    if scored[0][0] == 0:
        all_rels = sorted(
            str(p.relative_to(repo_path)).replace("\\", "/") for p in repo_path.rglob("*.py")
        )
        return all_rels[:limit]
    return [rel for _, rel in scored[:limit]]


class ScoutAgent(BaseAgent):
    name = "Scout"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        repo_path = Path(str(context.get("repo_path", ".")))
        candidate_files = _rank_py_files(repo_path, issue, limit=14)
        prompt = (
            "Given issue text and ranked candidate files, summarize likely impact zones.\n"
            f"Issue: {issue[:2800]}\nFiles: {candidate_files}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        return AgentResult(
            summary="Relevant code areas explored with keyword-aware ranking.",
            payload={
                "candidate_files": candidate_files,
                "scout_notes": response.text,
            },
            confidence=0.7,
        )
