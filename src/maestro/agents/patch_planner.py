from __future__ import annotations

from pathlib import Path
from typing import Any

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.file_excerpt import file_excerpt_for_llm
from maestro.agents.json_utils import extract_first_json_value
from maestro.agents.patch_safe import SnippetEdit


def _normalize_edits(raw: Any) -> list[SnippetEdit]:
    if not isinstance(raw, list):
        return []
    out: list[SnippetEdit] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("target_file") or "").strip()
        old_s = item.get("old_snippet") or item.get("old") or ""
        new_s = item.get("new_snippet") or item.get("new") or ""
        if not path or not isinstance(old_s, str) or not isinstance(new_s, str):
            continue
        if not old_s:
            continue
        out.append(SnippetEdit(path=path.replace("\\", "/"), old_snippet=old_s, new_snippet=new_s))
    return out


class PatchStrategistAgent(BaseAgent):
    """Ad-hoc agent: emits structured snippet edits (consumed by Surgeon)."""

    name = "PatchStrategist"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        repo_path = Path(str(context.get("repo_path", ".")))
        scout = context.get("scout", {})
        candidate_files: list[str] = []
        if isinstance(scout, dict):
            raw = scout.get("candidate_files", [])
            if isinstance(raw, list):
                candidate_files = [str(p) for p in raw]

        digest: list[str] = []
        for rel in candidate_files[:4]:
            body = file_excerpt_for_llm(repo_path, rel, head=160, tail=35, full_if_fewer_than=200)
            if body:
                digest.append(f"--- {rel} ---\n" + body)

        prompt = (
            "You are PatchPlanner. Propose minimal snippet replacements to fix the issue.\n"
            "Reply with JSON only:\n"
            '{"edits":[{"path":"relative/path.py","old_snippet":"exact text","new_snippet":"replacement"}],'
            '"notes":"short rationale"}\n'
            "Rules: old_snippet must be copied verbatim from excerpts (spaces, tabs, newlines) and match exactly once; "
            "prefer single-line exact replacements before multi-line blocks; stay within listed files; no refactors.\n\n"
            f"Issue:\n{issue}\n\nFile excerpts:\n{chr(10).join(digest)}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        parsed = extract_first_json_value(response.text)
        edits: list[SnippetEdit] = []
        notes = ""
        if isinstance(parsed, dict):
            notes = str(parsed.get("notes") or "")
            edits = _normalize_edits(parsed.get("edits"))

        summary = (
            f"Drafted {len(edits)} snippet edit(s) for Maestro routing."
            if edits
            else "No snippet-level plan produced."
        )
        payload = {
            "patch_plan": {
                "edits": [{"path": e.path, "old_snippet": e.old_snippet, "new_snippet": e.new_snippet} for e in edits],
                "notes": notes or response.text[:2000],
            },
            "planner_model": response.model,
        }
        return AgentResult(summary=summary, payload=payload, confidence=0.72 if edits else 0.4)


PatchPlannerAgent = PatchStrategistAgent
