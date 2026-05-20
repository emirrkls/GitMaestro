from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypedDict


class TestComparisonResult(TypedDict):
    """Structured baseline-vs-post-patch comparison outcome."""

    no_regression: bool
    issue_resolved: bool
    baseline_failures: list[str]
    new_failures: list[str]
    fixed_by_patch: list[str]
    summary: str
    # Scope-discipline fields. Populated only when target_failures was provided.
    # target_resolved: every issue-scoped failing test now passes.
    # scope_clean: no failures outside the target set were fixed by this patch
    # (out-of-scope fixes likely indicate the patch is doing too much).
    # unsolicited_fixes: baseline failures Scout flagged as out-of-scope that
    # nonetheless went green — informational only, surfaced to ReleaseScribe.
    # target_failures_seen: echo of the input set, so downstream agents can audit.
    target_resolved: bool
    scope_clean: bool
    unsolicited_fixes: list[str]
    target_failures_seen: list[str]


def extract_unittest_failure_labels(stderr: str) -> list[str]:
    """Parse unittest stderr for FAIL:/ERROR: lines."""
    labels: list[str] = []
    for line in stderr.splitlines():
        m = re.match(r"^(FAIL|ERROR):\s*(.+)$", line.strip())
        if m:
            labels.append(m.group(2).strip())
    return labels[:24]


def _normalize_label(label: str) -> str:
    """Strip whitespace and trailing dot for tolerant target/baseline matching."""
    return label.strip().rstrip(".").strip()


def _label_matches(target: str, candidate: str) -> bool:
    """Match Scout's dotted label against a unittest stderr label or vice versa.

    Scout emits ``test_x (module.Class.test_x)`` style labels.
    unittest stderr also uses that form, but the dotted suffix may carry an extra
    trailing dot from ``FAIL:`` headers. Treat substring containment in either
    direction as a match so partial Scout inputs (just the dotted id, or just
    the bare function name) still align.
    """
    t = _normalize_label(target)
    c = _normalize_label(candidate)
    if not t or not c:
        return False
    if t == c:
        return True
    return t in c or c in t


def _looks_like_test_identifier(label: str) -> bool:
    """Heuristic: unittest ids or FAIL-line labels mention ``test_`` or a class."""
    s = _normalize_label(label)
    return "test_" in s or ".Test" in s


def targets_already_passing(
    *,
    target_failures: list[str] | None,
    baseline: dict[str, Any] | None,
) -> bool:
    """Return True iff Scout supplied at least one target test AND none of those
    targets appear in the baseline failure set.

    Used by the conductor to short-circuit into an ``already_resolved`` terminal
    state instead of generating a patch for an issue that the baseline already
    proves is green. A missing baseline (``None``) is treated as "unknown" and
    returns ``False`` so we do not skip the normal flow when we have no proof.
    """
    if not target_failures:
        return False
    if baseline is None:
        return False
    if not any(_looks_like_test_identifier(t) for t in target_failures):
        # Scout sometimes emits human hint strings (e.g. repro prose) that never
        # appear in unittest stderr — cannot prove the target is already green.
        return False
    if not bool(baseline.get("passed")) and not str(baseline.get("stderr") or "").strip():
        # Baseline ran but emitted no stderr — we cannot prove targets pass.
        return False
    baseline_labels = set(extract_unittest_failure_labels(str(baseline.get("stderr") or "")))
    if bool(baseline.get("passed")):
        # Full green baseline; every target is by definition already passing.
        return True
    for target in target_failures:
        for bl in baseline_labels:
            if _label_matches(target, bl):
                return False
    return True


def _classify_target_overlap(
    target_failures: list[str] | None,
    baseline_labels: set[str],
) -> tuple[set[str], set[str]]:
    """Split the baseline failure set into in-scope (target) and out-of-scope.

    Returns ``(scoped_baseline, out_of_scope_baseline)``. Both are subsets of
    ``baseline_labels``. When ``target_failures`` is falsy, every baseline failure
    is treated as in-scope — this preserves the pre-scope-discipline behavior.
    """
    if not target_failures:
        return set(baseline_labels), set()
    scoped: set[str] = set()
    for bl in baseline_labels:
        if any(_label_matches(t, bl) for t in target_failures):
            scoped.add(bl)
    out_of_scope = set(baseline_labels) - scoped
    return scoped, out_of_scope


def compare_test_results(
    baseline: dict[str, Any] | None,
    post_patch: dict[str, Any],
    *,
    require_fix_on_red_baseline: bool = True,
    target_failures: list[str] | None = None,
) -> TestComparisonResult:
    """
    Compare baseline and post-patch unittest outcomes.

    When no baseline exists (or baseline passed), post-patch must fully pass.
    When baseline already failed, ``no_regression`` alone is insufficient: at least one
    baseline failure must be fixed (or all tests must pass) for ``issue_resolved``.

    ``target_failures`` lets callers carry Scout's issue-to-test mapping into the
    decision. Only baseline failures matching that set count toward ``issue_resolved``;
    failures outside the set surface via ``scope_clean`` / ``unsolicited_fixes``.
    When omitted, the legacy "all failing tests are targets" behavior applies.
    """
    target_seen = sorted({_normalize_label(t) for t in (target_failures or []) if str(t).strip()})
    post_passed = bool(post_patch.get("passed"))
    post_labels = set(extract_unittest_failure_labels(str(post_patch.get("stderr") or "")))

    if baseline is None or bool(baseline.get("passed")):
        issue_resolved = post_passed
        summary = (
            "Baseline clean; post-patch tests passed."
            if post_passed
            else "Baseline clean; post-patch tests failed."
        )
        return {
            "no_regression": issue_resolved,
            "issue_resolved": issue_resolved,
            "baseline_failures": [],
            "new_failures": sorted(post_labels),
            "fixed_by_patch": [],
            "summary": summary,
            "target_resolved": issue_resolved,
            "scope_clean": True,
            "unsolicited_fixes": [],
            "target_failures_seen": target_seen,
        }

    baseline_labels = set(extract_unittest_failure_labels(str(baseline.get("stderr") or "")))
    new_failures = sorted(post_labels - baseline_labels)
    fixed_by_patch_set = baseline_labels - post_labels
    fixed_by_patch = sorted(fixed_by_patch_set)
    no_regression = len(new_failures) == 0

    scoped_baseline, out_of_scope_baseline = _classify_target_overlap(
        target_failures, baseline_labels
    )
    scoped_post_failures = scoped_baseline & post_labels
    target_resolved = no_regression and len(scoped_baseline) > 0 and not scoped_post_failures
    if not target_failures:
        # Legacy mode: target == "any baseline failure". Mirror old logic so callers
        # without Scout data behave exactly as before.
        target_resolved = no_regression and bool(fixed_by_patch_set)

    unsolicited = sorted(out_of_scope_baseline & fixed_by_patch_set)
    scope_clean = len(unsolicited) == 0

    if post_passed:
        issue_resolved = True
    elif target_failures:
        # When Scout provided a target, ignore unrelated red noise — only target health matters.
        issue_resolved = target_resolved
    elif no_regression and fixed_by_patch:
        issue_resolved = True
    elif no_regression and not require_fix_on_red_baseline:
        issue_resolved = True
    else:
        issue_resolved = False

    if issue_resolved:
        if target_failures and not scope_clean:
            summary = (
                f"Issue resolved (scope-aware) but {len(unsolicited)} out-of-scope failure(s) "
                f"also went green; flag for review."
            )
        else:
            summary = (
                f"Issue resolved vs red baseline. fixed_by_patch={len(fixed_by_patch)}, "
                f"new_failures={len(new_failures)}."
            )
    elif no_regression:
        summary = (
            f"No regression but issue unresolved: {len(scoped_baseline) or len(baseline_labels)} "
            f"target failure(s) unchanged."
        )
    else:
        summary = f"Regression detected: {len(new_failures)} new failure(s) vs baseline."

    return {
        "no_regression": no_regression,
        "issue_resolved": issue_resolved,
        "baseline_failures": sorted(baseline_labels),
        "new_failures": new_failures,
        "fixed_by_patch": fixed_by_patch,
        "summary": summary,
        "target_resolved": target_resolved,
        "scope_clean": scope_clean,
        "unsolicited_fixes": unsolicited,
        "target_failures_seen": target_seen,
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

    parts.append(
        "Latest stderr (address the issue's described behavior, not only the assertion text):\n"
        + stderr[:max_body]
    )
    return "\n\n".join(parts)


def test_focus_files_for_context(stderr: str, workspace: Path) -> list[str]:
    """Relative paths to prioritize in Surgeon digest when repairing after test failure."""
    return relative_test_paths_mentioned(stderr, workspace, limit=8)
