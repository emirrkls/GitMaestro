from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CriticReviewRecord:
    decision: str
    confidence: float
    retry_index: int
    confidence_from_llm: bool = False


@dataclass
class AgenticFatigueTracker:
    """
    Tracks Critic decisions within a run to detect compromise-after-rejects patterns
    (agentic fatigue) without domain-specific rules.
    """

    records: list[CriticReviewRecord] = field(default_factory=list)

    def record(
        self,
        *,
        decision: str,
        confidence: float,
        retry_index: int,
        confidence_from_llm: bool = False,
    ) -> None:
        self.records.append(
            CriticReviewRecord(
                decision=decision.strip().lower(),
                confidence=confidence,
                retry_index=retry_index,
                confidence_from_llm=confidence_from_llm,
            )
        )

    def consecutive_rejects_before_latest(self) -> int:
        if len(self.records) < 2 or self.records[-1].decision != "approve":
            return 0
        count = 0
        for rec in reversed(self.records[:-1]):
            if rec.decision == "reject":
                count += 1
            else:
                break
        return count

    def evaluate_compromise(
        self,
        *,
        min_rejects: int,
        compromise_max_confidence: float,
        confidence_drop_min: float,
        require_both_signals: bool = True,
        require_explicit_confidence: bool = True,
    ) -> tuple[bool, str | None]:
        """
        True when the latest record is approve after repeated rejects with signs of
        lowered standards (low approve confidence and/or sharp drop vs prior rejects).

        When ``require_both_signals`` is True, both low confidence and a meaningful
        drop are required (fewer false positives). When ``require_explicit_confidence``
        is True, heuristic/default Critic confidence values are ignored.
        """
        if not self.records or self.records[-1].decision != "approve":
            return False, None

        latest = self.records[-1]
        if require_explicit_confidence and not latest.confidence_from_llm:
            return False, None

        streak = self.consecutive_rejects_before_latest()
        if streak < min_rejects:
            return False, None

        approve_conf = latest.confidence
        reject_confs = [r.confidence for r in self.records[-(streak + 1) : -1]]
        max_reject_conf = max(reject_confs) if reject_confs else 0.0
        drop = max_reject_conf - approve_conf

        low_confidence = approve_conf <= compromise_max_confidence
        confidence_drop = drop >= confidence_drop_min

        if require_both_signals:
            if not (low_confidence and confidence_drop):
                return False, None
            return True, "agentic_fatigue_compromise_after_rejects"
        if low_confidence:
            return True, "agentic_fatigue_low_confidence_approve_after_rejects"
        if confidence_drop:
            return True, "agentic_fatigue_confidence_drop_after_rejects"
        return False, None

    def summary(self) -> dict[str, object]:
        return {
            "review_count": len(self.records),
            "consecutive_rejects_before_approve": self.consecutive_rejects_before_latest(),
            "history": [
                {
                    "decision": r.decision,
                    "confidence": r.confidence,
                    "retry_index": r.retry_index,
                    "confidence_from_llm": r.confidence_from_llm,
                }
                for r in self.records
            ],
        }
