import unittest

from maestro.policies.agentic_fatigue import AgenticFatigueTracker
from maestro.policies.retry import critic_approve_allowed, is_final_retry
from maestro.policies.test_feedback import compare_test_results


class IssueResolvedPolicyTests(unittest.TestCase):
    def test_red_baseline_no_fix_is_not_resolved(self) -> None:
        baseline = {
            "passed": False,
            "stderr": "FAIL: test_hotel.TestHotel.test_cancel (test_hotel.py)\n",
        }
        post = {
            "passed": False,
            "stderr": "FAIL: test_hotel.TestHotel.test_cancel (test_hotel.py)\n",
        }
        cmp = compare_test_results(baseline, post, require_fix_on_red_baseline=True)
        self.assertTrue(cmp["no_regression"])
        self.assertFalse(cmp["issue_resolved"])

    def test_red_baseline_with_fix_is_resolved(self) -> None:
        baseline = {
            "passed": False,
            "stderr": "FAIL: test_a (t.py)\nFAIL: test_b (t.py)\n",
        }
        post = {"passed": False, "stderr": "FAIL: test_b (t.py)\n"}
        cmp = compare_test_results(baseline, post, require_fix_on_red_baseline=True)
        self.assertTrue(cmp["issue_resolved"])
        self.assertEqual(cmp["fixed_by_patch"], ["test_a (t.py)"])

    def test_clean_baseline_requires_full_pass(self) -> None:
        baseline = {"passed": True, "stderr": ""}
        post_fail = {"passed": False, "stderr": "FAIL: x (t.py)\n"}
        cmp = compare_test_results(baseline, post_fail)
        self.assertFalse(cmp["issue_resolved"])

    def test_final_retry_blocks_low_confidence_approve(self) -> None:
        ok, reason = critic_approve_allowed(
            decision="approve",
            confidence=0.78,
            retry_count=10,
            max_retries=10,
            final_retry_min_confidence=0.92,
        )
        self.assertFalse(ok)
        self.assertIsNotNone(reason)

    def test_fatigue_or_mode_still_available(self) -> None:
        t = AgenticFatigueTracker()
        for i in range(3):
            t.record(decision="reject", confidence=0.95, retry_index=i, confidence_from_llm=True)
        t.record(decision="approve", confidence=0.8, retry_index=3, confidence_from_llm=True)
        ok, reason = t.evaluate_compromise(
            min_rejects=3,
            compromise_max_confidence=0.5,
            confidence_drop_min=0.12,
            require_both_signals=False,
            require_explicit_confidence=True,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "agentic_fatigue_confidence_drop_after_rejects")

    def test_final_retry_allows_high_confidence(self) -> None:
        self.assertTrue(is_final_retry(3, 3))
        ok, _ = critic_approve_allowed(
            decision="approve",
            confidence=0.95,
            retry_count=3,
            max_retries=3,
            final_retry_min_confidence=0.92,
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
