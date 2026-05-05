from __future__ import annotations


def evaluate_safety_gate(context: dict[str, object]) -> dict[str, object]:
    patch = str(context.get("patch_diff", ""))
    feedback = context.get("critic_feedback", [])
    too_large = patch.count("\n") > 300
    has_secret_signal = any(token in patch.lower() for token in ("api_key", "secret", "private_key"))
    blocked = too_large or has_secret_signal
    reason = None
    if too_large:
        reason = "patch_scope_too_large"
    elif has_secret_signal:
        reason = "potential_secret_leak"
    return {
        "passed": not blocked,
        "reason": reason,
        "signals": {
            "line_count": patch.count("\n"),
            "feedback_items": len(feedback) if isinstance(feedback, list) else 0,
        },
    }
