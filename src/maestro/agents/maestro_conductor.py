from __future__ import annotations

from dataclasses import dataclass

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value

AGENT_ROSTER = """
Available specialists (dispatch exactly one per step when action=dispatch):
- IssueAnalyst: decompose issue into hypotheses, repro steps, and analysis notes.
- CodeExplorer: rank repository files and summarize impact zones.
- PatchStrategist: plan multi-snippet edits before patching (spawn when patch is complex).
- PatchAuthor: produce minimal unified-diff style edits in the workspace.
- PatchReviewer: approve/reject a candidate patch (requires patch_diff in context).
- TestVerifier: run automated tests (use task "baseline" before patch, "verify" after patch).
- ReleaseScribe: draft commit message and PR body after tests and safety pass.
""".strip()

_AGENT_NAMES = {
    "issueanalyst": "IssueAnalyst",
    "codeexplorer": "CodeExplorer",
    "patchstrategist": "PatchStrategist",
    "patchauthor": "PatchAuthor",
    "patchreviewer": "PatchReviewer",
    "testverifier": "TestVerifier",
    "releasescribe": "ReleaseScribe",
}

_VALID_ACTIONS = {
    "dispatch",
    "spawn_patch_strategist",
    "human_escalation",
    "finish_success",
    "finish_already_resolved",
    "finish_reject",
}


@dataclass(slots=True)
class ConductorDecision:
    action: str
    agent: str | None = None
    task: str = ""
    rationale: str = ""
    confidence: float = 0.75


class MaestroConductorAgent(BaseAgent):
    """Maestro — central conductor that routes work to specialists (Cursor-style)."""

    name = "Maestro"

    def decide(self, context: dict[str, object], *, situation_report: str) -> ConductorDecision:
        mock_mode = bool(context.get("mock_llm", False))
        if mock_mode:
            return self._mock_fallback(context)

        prompt = (
            "You are Maestro, the conductor orchestrating a multi-agent software repair crew.\n"
            "Read the situation report and choose the SINGLE best next step.\n"
            'Return JSON only: {"action":"dispatch|spawn_patch_strategist|human_escalation|'
            'finish_success|finish_already_resolved|finish_reject","agent":"name or null",'
            '"task":"short instruction","rationale":"why","confidence":0-1}\n'
            "Rules:\n"
            "- Prefer IssueAnalyst and CodeExplorer early if their outputs are missing.\n"
            "- Run TestVerifier baseline before first patch when pre-patch status unknown.\n"
            "- PatchReviewer only after PatchAuthor produced a material patch.\n"
            "- Do not finish_success until tests indicate issue_resolved.\n"
            "- Scope discipline: this run targets ONE issue. If the situation report shows a "
            "  'Scope warning' section, the patch fixed unrelated bugs; route back to PatchAuthor "
            "  with a revise_patch task to shrink the diff, or human_escalation if it cannot be "
            "  narrowed. Never finish_success on a scope-creeping patch.\n"
            "- Already-resolved short-circuit: if the situation report contains an "
            "  'Already-resolved signal' section, the baseline already shows the issue's target "
            "  tests passing. Do NOT author any patch. Dispatch ReleaseScribe with task "
            "  `draft_already_resolved_feedback` exactly once, then choose action "
            "  `finish_already_resolved`. Never run PatchAuthor in this case.\n"
            "- Use human_escalation when the issue is too vague or repeated failures stall progress.\n"
            "- spawn_patch_strategist at most once before a difficult patch attempt.\n\n"
            f"{AGENT_ROSTER}\n\n"
            f"Situation report:\n{situation_report[:12000]}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        parsed = extract_first_json_value(response.text)
        if isinstance(parsed, dict):
            action = str(parsed.get("action", "dispatch")).strip().lower()
            agent_raw = parsed.get("agent")
            agent = str(agent_raw).strip() if agent_raw is not None else None
            task = str(parsed.get("task", "")).strip()
            rationale = str(parsed.get("rationale", "")).strip() or "Conductor LLM decision."
            conf_raw = parsed.get("confidence")
            confidence = float(conf_raw) if isinstance(conf_raw, (int, float)) else 0.78
            if action in _AGENT_NAMES:
                agent = agent or _AGENT_NAMES[action]
                action = "dispatch"
                rationale = (
                    rationale
                    + " Normalized malformed conductor action that named an agent."
                )
            elif action not in _VALID_ACTIONS:
                fallback = self._heuristic_fallback(context)
                fallback.rationale = (
                    f"Invalid conductor action {action!r}; using heuristic fallback. "
                    + fallback.rationale
                )
                return fallback
            return ConductorDecision(
                action=action,
                agent=agent,
                task=task,
                rationale=rationale,
                confidence=confidence,
            )
        return self._heuristic_fallback(context)

    def run(self, context: dict[str, object]) -> AgentResult:
        """Legacy entry — not used by conductor loop."""
        decision = self.decide(context, situation_report=str(context.get("issue_text", "")))
        return AgentResult(
            summary=f"Conductor chose {decision.action}.",
            payload=decision.__dict__,
            confidence=decision.confidence,
        )

    def _mock_fallback(self, context: dict[str, object]) -> ConductorDecision:
        return self._heuristic_fallback(context)

    def _heuristic_fallback(self, context: dict[str, object]) -> ConductorDecision:
        issue = str(context.get("issue_text", "")).strip()
        if len(issue) < 12:
            return ConductorDecision(
                action="human_escalation",
                rationale="Issue text too short for safe automation.",
                confidence=0.9,
            )
        if not isinstance(context.get("analysis"), dict):
            return ConductorDecision(
                action="dispatch",
                agent="IssueAnalyst",
                task="decompose_issue",
                rationale="Issue not analyzed yet.",
            )
        if not isinstance(context.get("scout"), dict):
            return ConductorDecision(
                action="dispatch",
                agent="CodeExplorer",
                task="discover_code_context",
                rationale="Repository context not explored yet.",
            )
        if context.get("test_baseline_before_patch") and not isinstance(
            context.get("test_baseline"), dict
        ):
            return ConductorDecision(
                action="dispatch",
                agent="TestVerifier",
                task="baseline",
                rationale="Capture pre-patch test baseline.",
            )
        if bool(context.get("target_already_resolved")):
            if not isinstance(context.get("scribe"), dict):
                return ConductorDecision(
                    action="dispatch",
                    agent="ReleaseScribe",
                    task="draft_already_resolved_feedback",
                    rationale=(
                        "Baseline already proves the issue's target tests pass; "
                        "produce an already-resolved feedback report."
                    ),
                    confidence=0.92,
                )
            return ConductorDecision(
                action="finish_already_resolved",
                rationale=(
                    "Target tests already green in baseline; closing without a patch."
                ),
                confidence=0.94,
            )
        if not context.get("patch_approved"):
            retry = int(context.get("patch_retry_count", 0))
            max_retries = int(context.get("max_retries", 3))
            pending = str(context.get("pending_patch_diff", ""))
            if pending and not context.get("last_patch_review"):
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchReviewer",
                    task="review_patch",
                    rationale="Review candidate patch before testing.",
                )
            review = context.get("last_patch_review")
            if isinstance(review, dict) and str(review.get("decision")) == "reject":
                if retry < max_retries:
                    return ConductorDecision(
                        action="dispatch",
                        agent="PatchAuthor",
                        task="revise_patch",
                        rationale="Patch rejected; author should revise.",
                    )
                return ConductorDecision(
                    action="human_escalation",
                    rationale="Patch review retry budget exhausted.",
                    confidence=0.88,
                )
            if int(context.get("patch_strategist_spent", 0)) < int(
                context.get("ad_hoc_budget", 1)
            ) and str(context.get("complexity", "")) == "high":
                return ConductorDecision(
                    action="spawn_patch_strategist",
                    rationale="High complexity — plan patch before authoring.",
                )
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="author_patch",
                rationale="Author or revise patch.",
            )
        comparison = context.get("test_comparison")
        if isinstance(comparison, dict) and comparison.get("issue_resolved"):
            if not comparison.get("scope_clean", True) and bool(
                context.get("strict_scope_mode", True)
            ):
                # Patch fixed out-of-scope failures; ask PatchAuthor to shrink the diff
                # before we declare success on this issue.
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchAuthor",
                    task="revise_patch",
                    rationale=(
                        "Scope creep detected: patch fixed out-of-scope failures. "
                        "Revise to address only the targeted issue."
                    ),
                    confidence=0.7,
                )
            if not isinstance(context.get("scribe"), dict):
                return ConductorDecision(
                    action="dispatch",
                    agent="ReleaseScribe",
                    task="draft_commit_and_pr",
                    rationale="Tests resolved issue; draft release artifacts.",
                )
            return ConductorDecision(
                action="finish_success",
                rationale="Patch approved and tests resolved.",
                confidence=0.86,
            )
        repair = int(context.get("test_repair_attempt", 0))
        max_repair = int(context.get("test_repair_max_retries", 2))
        if repair < max_repair:
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="test_repair_patch",
                rationale="Tests failed; repair pass.",
            )
        if not isinstance(context.get("test_result"), dict):
            return ConductorDecision(
                action="dispatch",
                agent="TestVerifier",
                task="verify",
                rationale="Run post-patch verification tests.",
            )
        return ConductorDecision(
            action="finish_reject",
            rationale="Could not resolve issue within repair budget.",
            confidence=0.8,
        )
