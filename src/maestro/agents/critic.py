from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value
from maestro.policies.patch_signals import is_material_unified_diff


class CriticAgent(BaseAgent):
    name = "Critic"

    def run(self, context: dict[str, object]) -> AgentResult:
        retry_count = int(context.get("retry_count", 0))
        patch = str(context.get("patch_diff", ""))
        issue = str(context.get("issue_text", ""))

        critique_prompt = (
            "You review a proposed unified diff against the issue.\n"
            'Reply with JSON only: {"decision":"approve" or "reject", "confidence":0-1, '
            '"feedback":["bullet", ...], "evidence":["short reason", ...]}\n'
            "Approve when the diff is a plausible minimal fix aligned with the issue (including obvious typo/logic tweaks); "
            "numeric edge cases and full correctness will be validated by automated tests next — do not reject solely "
            "because you are unsure about a specific expected number.\n"
            "Reject if the patch is empty, clearly unrelated to the issue, deletes large unrelated code, or has "
            "obviously broken Python/JS structure (wrong indentation destroying a block).\n\n"
            f"Issue excerpt:\n{issue[:2800]}\n\nPatch:\n{patch[:12000]}"
        )
        response = self.llm.complete(model=self.model, prompt=critique_prompt)

        parsed = extract_first_json_value(response.text)
        decision = ""
        confidence = None
        feedback: list[str] = []
        evidence: list[str] = []

        if isinstance(parsed, dict):
            raw_decision = parsed.get("decision")
            if isinstance(raw_decision, str):
                decision = raw_decision.strip().lower()
            dc = parsed.get("confidence")
            if isinstance(dc, (int, float)):
                confidence = float(dc)
            fb = parsed.get("feedback")
            if isinstance(fb, list):
                feedback = [str(x) for x in fb][:12]
            ev = parsed.get("evidence")
            if isinstance(ev, list):
                evidence = [str(x) for x in ev][:8]

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
            else:
                decision = "approve"
                feedback = feedback or ["Structural patch present; Tester will validate behavior."]
                evidence = evidence or ["unified_diff_signal", f"retry_count={retry_count}"]

        if confidence is None:
            confidence = 0.78 if decision == "approve" else 0.66

        return AgentResult(
            summary=f"Patch review completed with {decision}.",
            payload={
                "decision": decision,
                "confidence": confidence,
                "evidence": evidence or ["llm_or_heuristic"],
                "feedback": feedback,
                "critic_model": response.model,
            },
            confidence=confidence,
        )
