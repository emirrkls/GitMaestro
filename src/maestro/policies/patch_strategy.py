from __future__ import annotations

from dataclasses import dataclass


ChangeScale = str


@dataclass(slots=True)
class PatchStrategyConfig:
    max_diff_lines: int
    max_diff_bytes: int
    rewrite_enabled: bool
    hunk_enabled: bool
    snippet_enabled: bool


def classify_change_scale(context: dict[str, object]) -> ChangeScale:
    issue_text = str(context.get("issue_text", ""))
    scout = context.get("scout")
    baseline = context.get("test_baseline")
    complexity = str(context.get("complexity", "")).strip().lower()
    issue_len = len(issue_text)

    candidate_files = 0
    if isinstance(scout, dict):
        raw = scout.get("candidate_files")
        if isinstance(raw, list):
            candidate_files = len(raw)

    baseline_failed = isinstance(baseline, dict) and not bool(baseline.get("passed", True))
    baseline_stderr = ""
    if isinstance(baseline, dict):
        baseline_stderr = str(baseline.get("stderr") or "")

    failing_hints = baseline_stderr.count("FAILED") + baseline_stderr.count("ERROR")
    if baseline_stderr:
        failing_hints += baseline_stderr.count("FAIL:") + baseline_stderr.count("ERROR:")
    if complexity == "high" or candidate_files >= 5 or issue_len > 900 or failing_hints >= 3:
        return "broad_refactor"
    if baseline_failed or candidate_files >= 3 or issue_len > 350:
        return "localized_refactor"
    return "small_fix"


def strategies_for_scale(scale: ChangeScale, cfg: PatchStrategyConfig) -> list[str]:
    selected: list[str] = []
    if cfg.snippet_enabled:
        selected.append("snippet")
    if scale in ("localized_refactor", "broad_refactor") and cfg.hunk_enabled:
        selected.append("hunk")
    if scale == "broad_refactor" and cfg.rewrite_enabled:
        selected.append("rewrite")
    return selected or ["snippet"]
