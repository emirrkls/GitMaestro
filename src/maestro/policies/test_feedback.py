from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypedDict


class TestComparisonResult(TypedDict):
    """Structured baseline-vs-post-patch comparison outcome."""

    no_regression: bool
    baseline_failures: list[str]
    new_failures: list[str]
    fixed_by_patch: list[str]
    summary: str


def extract_unittest_failure_labels(stderr: str) -> list[str]:
    """Parse unittest stderr for FAIL:/ERROR: lines."""
    labels: list[str] = []
    for line in stderr.splitlines():
        m = re.match(r"^(FAIL|ERROR):\s*(.+)$", line.strip())
        if m:
            labels.append(m.group(2).strip())
    return labels[:24]


def compare_test_results(
    baseline: dict[str, Any] | None,
    post_patch: dict[str, Any],
) -> TestComparisonResult:
    """
    Compare baseline and post-patch unittest outcomes.

    When no baseline exists (or baseline passed), behavior remains strict:
    post-patch must fully pass.
    """
    post_passed = bool(post_patch.get("passed"))
    post_labels = set(extract_unittest_failure_labels(str(post_patch.get("stderr") or "")))

    if baseline is None or bool(baseline.get("passed")):
        no_regression = post_passed
        summary = (
            "Baseline clean; post-patch tests passed."
            if post_passed
            else "Baseline clean; post-patch tests failed."
        )
        return {
            "no_regression": no_regression,
            "baseline_failures": [],
            "new_failures": sorted(post_labels),
            "fixed_by_patch": [],
            "summary": summary,
        }

    baseline_labels = set(extract_unittest_failure_labels(str(baseline.get("stderr") or "")))
    new_failures = sorted(post_labels - baseline_labels)
    fixed_by_patch = sorted(baseline_labels - post_labels)
    no_regression = len(new_failures) == 0
    summary = (
        f"No regression vs baseline. Pre-existing failures={len(baseline_labels)}, "
        f"new_failures={len(new_failures)}, fixed_by_patch={len(fixed_by_patch)}."
        if no_regression
        else f"Regression detected: {len(new_failures)} new failure(s) vs baseline."
    )
    return {
        "no_regression": no_regression,
        "baseline_failures": sorted(baseline_labels),
        "new_failures": new_failures,
        "fixed_by_patch": fixed_by_patch,
        "summary": summary,
    }


def relative_test_paths_mentioned(stderr: str, workspace: Path, *, limit: int = 6) -> list[str]:
    """Find test_*.py filenames in traceback text and map to paths under workspace."""
    names = sorted(set(re.findall(r"\b(test[\w]*\.py)\b", stderr, flags=re.IGNORECASE)))
    out: list[str] = []
    for name in names[:limit]:
        for p in workspace.rglob(name):
            try:
                rel = p.relative_to(workspace.resolve())
            except ValueError:
                continue
            s = str(rel).replace("\\", "/")
            if s not in out:
                out.append(s)
            break
    return out


def build_test_repair_feedback(
    baseline: dict[str, Any] | None,
    failure_payload: dict[str, Any],
    *,
    workspace: Path,
    max_body: int = 5200,
) -> str:
    """Human/LLM-readable block for Surgeon after tests fail on the patched tree."""
    stderr = str(failure_payload.get("stderr") or "")
    cmd = str(failure_payload.get("command") or "N/A")
    labels = extract_unittest_failure_labels(stderr)
    test_paths = relative_test_paths_mentioned(stderr, workspace)

    parts: list[str] = [
        f"Test command: {cmd}",
        f"Exit code: {failure_payload.get('exit_code')}",
    ]
    if labels:
        parts.append("Failing cases:\n- " + "\n- ".join(labels))
    if test_paths:
        parts.append("Traceback references these test modules (read matching source under repo root):\n- " + "\n- ".join(test_paths))

    if baseline is not None:
        base_ok = bool(baseline.get("passed"))
        parts.append(
            f"Pre-patch baseline: tests {'PASSED' if base_ok else 'ALREADY FAILING'} "
            f"(command={baseline.get('command')!r}, exit={baseline.get('exit_code')})."
        )
        if not base_ok:
            berr = str(baseline.get("stderr") or "")[:1800]
            if berr.strip():
                parts.append("Baseline stderr excerpt:\n" + berr)

    parts.append("Latest stderr (fix without regressing passing tests):\n" + stderr[:max_body])
    return "\n\n".join(parts)


def test_focus_files_for_context(stderr: str, workspace: Path) -> list[str]:
    """Relative paths to prioritize in Surgeon digest when repairing after test failure."""
    return relative_test_paths_mentioned(stderr, workspace, limit=8)
