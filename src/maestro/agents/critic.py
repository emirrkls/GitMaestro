from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value
from maestro.policies.patch_signals import is_material_unified_diff
from maestro.policies.retry import critic_approve_allowed, is_final_retry


class PatchReviewerAgent(BaseAgent):
    name = "PatchReviewer"

    def run(self, context: dict[str, object]) -> AgentResult:
        retry_count = int(context.get("retry_count", 0))
        max_retries = int(context.get("max_retries", 3))
        patch = str(context.get("patch_diff", ""))
        issue = str(context.get("issue_text", ""))
        final_min_conf = float(context.get("critic_final_retry_min_confidence", 0.92))

        critique_prompt = (
            "You review a proposed unified diff against the issue.\n"
            'Reply with JSON only: {"decision":"approve" or "reject", "confidence":0-1, '
            '"feedback":["bullet", ...], "evidence":["short reason", ...]}\n'
            "Approve only when the diff plausibly addresses what the issue describes, with minimal scope.\n"
            "Reject if the patch is empty, unrelated, structurally broken, or appears to work around "
            "tests/assertions instead of fixing the underlying behavior described in the issue.\n"
            "Reject large unrelated deletions or changes that narrow public behavior without justification.\n"
            "Base your judgment on the issue text and the diff — not on assumptions about specific domains.\n\n"
            f"Issue excerpt:\n{issue[:2800]}\n\nPatch:\n{patch[:12000]}"
        )
        response = self.llm.complete(model=self.model, prompt=critique_prompt)

        parsed = extract_first_json_value(response.text)
        decision = ""
        confidence = None
        confidence_from_llm = False
        feedback: list[str] = []
        evidence: list[str] = []

        if isinstance(parsed, dict):
            raw_decision = parsed.get("decision")
            if isinstance(raw_decision, str):
                decision = raw_decision.strip().lower()
            dc = parsed.get("confidence")
            if isinstance(dc, (int, float)):
                confidence = float(dc)
                confidence_from_llm = True
            fb = parsed.get("feedback")
            if isinstance(fb, list):
                feedback = [str(x) for x in fb][:12]
            ev = parsed.get("evidence")
            if isinstance(ev, list):
                evidence = [str(x) for x in ev][:8]

        final_retry = is_final_retry(retry_count, max_retries)

        if decision not in ("approve", "reject"):
            mock_mode = bool(context.get("mock_llm", False))
            material = is_material_unified_diff(patch)
            if not material:
                decision = "reject"
                evidence = evidence or ["no_material_unified_diff"]
                feedback = feedback or ["Need a precise minimal edit anchored in workspace files."]
            elif mock_mode and retry_count == 0 and material:
                decision = "reject"
                feedback = feedback or ["Mock mode: forcing an extra Surgeon refinement pass."]
                evidence = evidence or ["policy_mock_second_pass"]
            elif final_retry:
                decision = "reject"
                feedback = feedback or [
                    "Final retry requires an explicit LLM approve with high confidence."
                ]
                evidence = evidence or ["policy_final_retry_no_heuristic_approve"]
            else:
                decision = "approve"
                feedback = feedback or ["Structural patch present; verify behavior in tests."]
                evidence = evidence or ["unified_diff_signal", f"retry_count={retry_count}"]

        if confidence is None:
            confidence = 0.72 if decision == "approve" else 0.66

        allowed, block_reason = critic_approve_allowed(
            decision=decision,
            confidence=confidence,
            retry_count=retry_count,
            max_retries=max_retries,
            final_retry_min_confidence=final_min_conf,
        )
        if not allowed and block_reason:
            decision = "reject"
            evidence = evidence or [block_reason]
            feedback = feedback or [
                f"Approve blocked on final retry: confidence {confidence:.2f} "
                f"< required {final_min_conf:.2f}."
            ]

        return AgentResult(
            summary=f"Patch review completed with {decision}.",
            payload={
                "decision": decision,
                "confidence": confidence,
                "confidence_from_llm": confidence_from_llm,
                "evidence": evidence or ["llm_or_heuristic"],
                "feedback": feedback,
                "critic_model": response.model,
            },
            confidence=confidence,
        )


CriticAgent = PatchReviewerAgent
