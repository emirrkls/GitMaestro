import unittest

from maestro.policies.agentic_fatigue import AgenticFatigueTracker


class AgenticFatigueTests(unittest.TestCase):
    def _params(self) -> dict[str, object]:
        return {
            "min_rejects": 3,
            "compromise_max_confidence": 0.78,
            "confidence_drop_min": 0.18,
            "require_both_signals": True,
            "require_explicit_confidence": True,
        }

    def test_no_escalate_on_first_approve(self) -> None:
        t = AgenticFatigueTracker()
        t.record(decision="approve", confidence=0.9, retry_index=0, confidence_from_llm=True)
        ok, reason = t.evaluate_compromise(**self._params())  # type: ignore[arg-type]
        self.assertFalse(ok)
        self.assertIsNone(reason)

    def test_escalate_benchmark_fatigue_pattern(self) -> None:
        t = AgenticFatigueTracker()
        for i in range(3):
            t.record(decision="reject", confidence=1.0, retry_index=i, confidence_from_llm=True)
        t.record(decision="approve", confidence=0.78, retry_index=3, confidence_from_llm=True)
        ok, reason = t.evaluate_compromise(**self._params())  # type: ignore[arg-type]
        self.assertTrue(ok)
        self.assertEqual(reason, "agentic_fatigue_compromise_after_rejects")

    def test_no_escalate_without_explicit_confidence(self) -> None:
        t = AgenticFatigueTracker()
        for i in range(3):
            t.record(decision="reject", confidence=1.0, retry_index=i, confidence_from_llm=False)
        t.record(decision="approve", confidence=0.72, retry_index=3, confidence_from_llm=False)
        ok, _ = t.evaluate_compromise(**self._params())  # type: ignore[arg-type]
        self.assertFalse(ok)

    def test_no_escalate_when_only_low_confidence(self) -> None:
        t = AgenticFatigueTracker()
        for i in range(3):
            t.record(decision="reject", confidence=0.7, retry_index=i, confidence_from_llm=True)
        t.record(decision="approve", confidence=0.77, retry_index=3, confidence_from_llm=True)
        ok, _ = t.evaluate_compromise(**self._params())  # type: ignore[arg-type]
        self.assertFalse(ok)

    def test_no_escalate_two_rejects_only(self) -> None:
        t = AgenticFatigueTracker()
        t.record(decision="reject", confidence=1.0, retry_index=0, confidence_from_llm=True)
        t.record(decision="reject", confidence=1.0, retry_index=1, confidence_from_llm=True)
        t.record(decision="approve", confidence=0.75, retry_index=2, confidence_from_llm=True)
        ok, _ = t.evaluate_compromise(**self._params())  # type: ignore[arg-type]
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
