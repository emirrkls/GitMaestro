from __future__ import annotations


def should_retry(*, critic_decision: str, retry_count: int, max_retries: int) -> bool:
    return critic_decision == "reject" and retry_count < max_retries
