from __future__ import annotations


def should_retry(*, critic_decision: str, retry_count: int, max_retries: int) -> bool:
    return critic_decision == "reject" and retry_count < max_retries


def is_final_retry(retry_count: int, max_retries: int) -> bool:
    return retry_count >= max_retries


def critic_approve_allowed(
    *,
    decision: str,
    confidence: float | None,
    retry_count: int,
    max_retries: int,
    final_retry_min_confidence: float,
) -> tuple[bool, str | None]:
    """Block low-confidence approves on the final retry (agentic fatigue guard)."""
    if decision != "approve":
        return True, None
    if not is_final_retry(retry_count, max_retries):
        return True, None
    conf = confidence if confidence is not None else 0.0
    if conf < final_retry_min_confidence:
        return False, f"final_retry_confidence_below_{final_retry_min_confidence}"
    return True, None
