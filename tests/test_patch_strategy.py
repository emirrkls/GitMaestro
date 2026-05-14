import unittest

from maestro.policies.patch_strategy import PatchStrategyConfig, classify_change_scale, strategies_for_scale


class PatchStrategyTests(unittest.TestCase):
    def test_classify_small_fix(self) -> None:
        scale = classify_change_scale(
            {"issue_text": "Fix typo", "scout": {"candidate_files": ["a.py"]}, "complexity": "low"}
        )
        self.assertEqual(scale, "small_fix")

    def test_classify_broad_refactor(self) -> None:
        scale = classify_change_scale(
            {
                "issue_text": "x" * 1200,
                "scout": {"candidate_files": ["a.py", "b.py", "c.py", "d.py", "e.py"]},
                "complexity": "high",
            }
        )
        self.assertEqual(scale, "broad_refactor")

    def test_classify_broad_on_many_baseline_failures(self) -> None:
        scale = classify_change_scale(
            {
                "issue_text": "Fix totals",
                "scout": {"candidate_files": ["a.py"]},
                "complexity": "low",
                "test_baseline": {
                    "passed": False,
                    "stderr": "FAIL: a\nERROR: b\nFAIL: c\n",
                },
            }
        )
        self.assertEqual(scale, "broad_refactor")

    def test_strategy_order_for_broad(self) -> None:
        cfg = PatchStrategyConfig(
            max_diff_lines=500,
            max_diff_bytes=100000,
            rewrite_enabled=True,
            hunk_enabled=True,
            snippet_enabled=True,
        )
        self.assertEqual(strategies_for_scale("broad_refactor", cfg), ["snippet", "hunk", "rewrite"])


if __name__ == "__main__":
    unittest.main()
