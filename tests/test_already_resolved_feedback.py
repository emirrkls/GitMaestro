"""Tests for the already-resolved feedback path.

Covers:
- ReleaseScribe building an ``issue_feedback_markdown`` payload with an
  idempotency marker when its task is ``draft_already_resolved_feedback``.
- The conductor heuristic short-circuiting to ``finish_already_resolved`` once
  Scout's targets are green in the baseline.
"""

from __future__ import annotations

import unittest

from maestro.agents.maestro_conductor import MaestroConductorAgent
from maestro.agents.scribe import ReleaseScribeAgent


class _StubLLM:
    def complete(self, **_kwargs: object) -> object:
        class _R:
            text = "{}"

        return _R()


class AlreadyResolvedScribeTests(unittest.TestCase):
    def test_scribe_emits_feedback_markdown_with_marker(self) -> None:
        agent = ReleaseScribeAgent(llm=_StubLLM(), model="m")
        ctx = {
            "scribe_task": "draft_already_resolved_feedback",
            "issue_ref": "9",
            "issue_text": "Invoice extra charges leak across customers.",
            "task_id": "20260520-abcdef",
            "test_baseline": {
                "passed": False,
                "command": "python -m unittest test_hotel_system",
                "exit_code": 1,
                "stderr": "FAIL: test_other (mod.T.test_other)\n",
            },
            "target_already_resolved_targets": [
                "test_invoice_extra_charges_isolation "
                "(test_hotel_system.TestHotelReservationSystem.test_invoice_extra_charges_isolation)"
            ],
        }
        result = agent.run(ctx)
        payload = result.payload

        self.assertEqual(payload["feedback_kind"], "already_resolved")
        self.assertIn("issue_feedback_markdown", payload)
        self.assertIn("already resolved", payload["issue_feedback_markdown"])
        self.assertIn(
            "test_invoice_extra_charges_isolation",
            payload["issue_feedback_markdown"],
        )

        marker = payload["issue_comment_marker"]
        self.assertTrue(marker.startswith("<!--"))
        self.assertIn("run-id=20260520-abcdef", marker)
        self.assertIn("reason=already_resolved", marker)
        self.assertIn(marker, payload["issue_comment_body"])


class AlreadyResolvedConductorTests(unittest.TestCase):
    def test_heuristic_dispatches_scribe_then_finishes(self) -> None:
        conductor = MaestroConductorAgent(llm=_StubLLM(), model="m")
        ctx_base: dict[str, object] = {
            "mock_llm": True,
            "issue_text": "Long enough description of the bug to pass guards.",
            "analysis": {"analysis": "x"},
            "scout": {"target_test_labels": ["t.T.target"]},
            "test_baseline": {"passed": True},
            "test_baseline_before_patch": True,
            "target_already_resolved": True,
            "target_already_resolved_targets": ["t.T.target"],
        }

        first = conductor.decide(ctx_base, situation_report="report")
        self.assertEqual(first.action, "dispatch")
        self.assertEqual(first.agent, "ReleaseScribe")
        self.assertEqual(first.task, "draft_already_resolved_feedback")

        ctx_after_scribe = dict(ctx_base)
        ctx_after_scribe["scribe"] = {"feedback_kind": "already_resolved"}
        second = conductor.decide(ctx_after_scribe, situation_report="report")
        self.assertEqual(second.action, "finish_already_resolved")


if __name__ == "__main__":
    unittest.main()
