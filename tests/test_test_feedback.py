import tempfile
import unittest
from pathlib import Path

from maestro.policies.test_feedback import (
    build_test_repair_feedback,
    compare_test_results,
    extract_unittest_failure_labels,
    relative_test_paths_mentioned,
    targets_already_passing,
)


class TestFeedbackTests(unittest.TestCase):
    def test_extract_failure_labels(self) -> None:
        stderr = "FAIL: test_cart.TestShoppingCart.test_empty (test_cart.py)\nERROR: test_cart.TestShoppingCart.x\n"
        labels = extract_unittest_failure_labels(stderr)
        self.assertIn("test_cart.TestShoppingCart.test_empty (test_cart.py)", labels)
        self.assertIn("test_cart.TestShoppingCart.x", labels)

    def test_relative_paths_from_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "test_cart.py").write_text("# t\n", encoding="utf-8")
            stderr = r'File "C:\proj\test_cart.py", line 21, in test_empty'
            found = relative_test_paths_mentioned(stderr, root)
            self.assertEqual(found, ["test_cart.py"])

    def test_build_repair_feedback_includes_baseline_note(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fb = build_test_repair_feedback(
                {"passed": False, "command": "python -m unittest x", "exit_code": 1, "stderr": "baseline err"},
                {"command": "python -m unittest x", "exit_code": 1, "stderr": "FAIL: a.b.c\n"},
                workspace=root,
            )
            self.assertIn("Pre-patch baseline", fb)
            self.assertIn("ALREADY FAILING", fb)
            self.assertIn("FAIL: a.b.c", fb)


class ScopeAwareCompareTests(unittest.TestCase):
    """Scope-discipline behavior — target_failures filter the issue_resolved decision."""

    def test_target_only_pass_marks_resolved_even_with_other_reds(self) -> None:
        # Hotel scenario: only the overcharge test belongs to this issue.
        baseline = {
            "passed": False,
            "stderr": (
                "FAIL: test_cancel_frees_room (test_hotel.TestHotel.test_cancel_frees_room)\n"
                "FAIL: test_invoice_extra_charges_isolation "
                "(test_hotel.TestHotel.test_invoice_extra_charges_isolation)\n"
                "FAIL: test_negative_nights_validation "
                "(test_hotel.TestHotel.test_negative_nights_validation)\n"
            ),
        }
        # Post-patch: only the targeted test went green; the other two are still red.
        post = {
            "passed": False,
            "stderr": (
                "FAIL: test_cancel_frees_room (test_hotel.TestHotel.test_cancel_frees_room)\n"
                "FAIL: test_negative_nights_validation "
                "(test_hotel.TestHotel.test_negative_nights_validation)\n"
            ),
        }
        cmp = compare_test_results(
            baseline,
            post,
            target_failures=[
                "test_invoice_extra_charges_isolation "
                "(test_hotel.TestHotel.test_invoice_extra_charges_isolation)"
            ],
        )
        self.assertTrue(cmp["issue_resolved"], cmp["summary"])
        self.assertTrue(cmp["target_resolved"])
        self.assertTrue(cmp["scope_clean"])
        self.assertEqual(cmp["unsolicited_fixes"], [])

    def test_scope_creep_flagged_when_unrelated_failures_also_fixed(self) -> None:
        baseline = {
            "passed": False,
            "stderr": (
                "FAIL: test_cancel_frees_room (mod.TestX.test_cancel_frees_room)\n"
                "FAIL: test_invoice_extra_charges_isolation "
                "(mod.TestX.test_invoice_extra_charges_isolation)\n"
            ),
        }
        # Patch fixed BOTH tests — only one was the issue's target.
        post = {"passed": True, "stderr": ""}
        cmp = compare_test_results(
            baseline,
            post,
            target_failures=[
                "test_invoice_extra_charges_isolation "
                "(mod.TestX.test_invoice_extra_charges_isolation)"
            ],
        )
        self.assertTrue(cmp["issue_resolved"])
        self.assertFalse(cmp["scope_clean"])
        self.assertIn(
            "test_cancel_frees_room (mod.TestX.test_cancel_frees_room)",
            cmp["unsolicited_fixes"],
        )

    def test_target_still_red_blocks_resolution(self) -> None:
        baseline = {
            "passed": False,
            "stderr": (
                "FAIL: test_a (mod.TestX.test_a)\nFAIL: test_b (mod.TestX.test_b)\n"
            ),
        }
        # Patch fixed an unrelated test but the target is still failing.
        post = {"passed": False, "stderr": "FAIL: test_a (mod.TestX.test_a)\n"}
        cmp = compare_test_results(
            baseline,
            post,
            target_failures=["test_a (mod.TestX.test_a)"],
        )
        self.assertFalse(cmp["issue_resolved"])
        self.assertFalse(cmp["target_resolved"])

    def test_targets_already_passing_when_baseline_green(self) -> None:
        baseline = {"passed": True, "stderr": ""}
        self.assertTrue(
            targets_already_passing(
                target_failures=["test_invoice_extra_charges_isolation (m.T.t)"],
                baseline=baseline,
            )
        )

    def test_targets_already_passing_when_baseline_only_has_unrelated_reds(self) -> None:
        baseline = {
            "passed": False,
            "stderr": "FAIL: test_other (m.T.test_other)\n",
        }
        self.assertTrue(
            targets_already_passing(
                target_failures=["test_invoice_extra_charges_isolation (m.T.t)"],
                baseline=baseline,
            )
        )

    def test_targets_not_already_passing_when_target_is_red(self) -> None:
        baseline = {
            "passed": False,
            "stderr": (
                "FAIL: test_invoice_extra_charges_isolation "
                "(m.T.test_invoice_extra_charges_isolation)\n"
            ),
        }
        self.assertFalse(
            targets_already_passing(
                target_failures=[
                    "test_invoice_extra_charges_isolation "
                    "(m.T.test_invoice_extra_charges_isolation)"
                ],
                baseline=baseline,
            )
        )

    def test_targets_not_already_passing_when_only_hint_label_would_mismatch(self) -> None:
        """Regression: Scout hint strings must not mask a red dotted target."""
        baseline = {
            "passed": False,
            "stderr": (
                "FAIL: test_cancel_frees_room "
                "(test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room)\n"
            ),
        }
        # Hint text does NOT appear in stderr — must not claim already resolved.
        self.assertFalse(
            targets_already_passing(
                target_failures=["Book a room, cancel it, then try to book it again."],
                baseline=baseline,
            )
        )
        # Canonical dotted id DOES match stderr — still failing, not resolved.
        self.assertFalse(
            targets_already_passing(
                target_failures=[
                    "test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room"
                ],
                baseline=baseline,
            )
        )

    def test_targets_already_passing_requires_targets(self) -> None:
        self.assertFalse(
            targets_already_passing(target_failures=None, baseline={"passed": True})
        )
        self.assertFalse(
            targets_already_passing(target_failures=[], baseline={"passed": True})
        )

    def test_legacy_mode_when_no_targets_given(self) -> None:
        # Without target_failures, behavior matches the original "any fix resolves" rule.
        baseline = {
            "passed": False,
            "stderr": "FAIL: test_a (t.py)\nFAIL: test_b (t.py)\n",
        }
        post = {"passed": False, "stderr": "FAIL: test_b (t.py)\n"}
        cmp = compare_test_results(baseline, post)
        self.assertTrue(cmp["issue_resolved"])
        self.assertTrue(cmp["scope_clean"])  # no targets → no scope concerns
        self.assertEqual(cmp["target_failures_seen"], [])


if __name__ == "__main__":
    unittest.main()
