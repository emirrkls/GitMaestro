import unittest

from maestro.core.score import build_initial_score


class ScoreRoutingTests(unittest.TestCase):
    def test_score_complexity_and_movements(self) -> None:
        low = build_initial_score("bug-12345", ad_hoc_budget=1, max_retries=3)
        self.assertEqual(low.complexity, "low")
        self.assertTrue(any(m.agent == "PatchReviewer" for m in low.movements))

        high = build_initial_score("security-crash-777", ad_hoc_budget=1, max_retries=3)
        self.assertEqual(high.complexity, "high")
        self.assertTrue(any(m.agent == "PatchStrategist" for m in high.movements))

        ambiguous = build_initial_score("12", ad_hoc_budget=1, max_retries=3)
        self.assertEqual(ambiguous.complexity, "ambiguous")


if __name__ == "__main__":
    unittest.main()
