from __future__ import annotations

from typing import Any

from maestro.policies.patch_signals import is_material_unified_diff as is_material_patch


def _block(title: str, body: str) -> str:
    body = body.strip()
    if not body:
        return ""
    return f"### {title}\n{body}\n"


def build_maestro_situation_report(context: dict[str, Any]) -> str:
    """Compact state summary for Maestro conductor decisions."""
    parts: list[str] = [
        _block("Issue", str(context.get("issue_text", ""))[:3500]),
    ]

    phase_flags: list[str] = []
    analysis = context.get("analysis")
    if isinstance(analysis, dict):
        phase_flags.append("analysis=DONE")
        parts.append(_block("Issue analysis", str(analysis.get("analysis", ""))[:2000]))
        hy = analysis.get("hypotheses")
        if isinstance(hy, list) and hy:
            parts.append(_block("Hypotheses", "\n".join(f"- {h}" for h in hy[:8])))
    else:
        phase_flags.append("analysis=PENDING")

    scout = context.get("scout")
    if isinstance(scout, dict):
        phase_flags.append("code_exploration=DONE")
        files = scout.get("candidate_files", [])
        if isinstance(files, list) and files:
            parts.append(_block("Candidate files", "\n".join(f"- {f}" for f in files[:12])))
        target_labels = scout.get("target_test_labels")
        if isinstance(target_labels, list) and target_labels:
            source = scout.get("target_selection_source", "unknown")
            parts.append(
                _block(
                    f"Issue-scoped target tests (source={source})",
                    "\n".join(f"- {label}" for label in target_labels[:8]),
                )
            )
        notes = scout.get("scout_notes")
        if isinstance(notes, str) and notes.strip():
            parts.append(_block("Explorer notes", notes[:1500]))
    else:
        phase_flags.append("code_exploration=PENDING")
    baseline = context.get("test_baseline")
    if isinstance(baseline, dict):
        phase_flags.append("test_baseline=DONE")
        parts.append(
            _block(
                "Pre-patch tests (ALREADY RAN - do NOT re-run baseline)",
                f"passed={baseline.get('passed')} command={baseline.get('command')!r}",
            )
        )
    else:
        phase_flags.append("test_baseline=PENDING")
    test_result = context.get("test_result")
    if isinstance(test_result, dict):
        parts.append(
            _block(
                "Latest tests",
                f"passed={test_result.get('passed')} command={test_result.get('command')!r}",
            )
        )
    comparison = context.get("test_comparison")
    if isinstance(comparison, dict):
        parts.append(_block("Test policy", str(comparison.get("summary", ""))))
        if not comparison.get("scope_clean", True):
            unsolicited = comparison.get("unsolicited_fixes", [])
            parts.append(
                _block(
                    "Scope warning",
                    "Patch fixed failures outside the issue's target set: "
                    + ", ".join(str(x) for x in unsolicited[:8])
                    + ". Treat these as separate issues, not part of this PR.",
                )
            )
    if bool(context.get("target_already_resolved")):
        targets = context.get("target_already_resolved_targets") or []
        target_list = ", ".join(str(t) for t in targets if str(t).strip()) if isinstance(targets, list) else ""
        parts.append(
            _block(
                "Already-resolved signal",
                "The baseline test run shows the issue's Scout-selected target tests "
                "ALREADY pass. Do NOT author a patch. Dispatch ReleaseScribe with task "
                "`draft_already_resolved_feedback`, then choose action "
                "`finish_already_resolved`. Targets: "
                + (target_list or "(see Scout output)"),
            )
        )
    patch_plan = context.get("patch_plan")
    if isinstance(patch_plan, dict):
        phase_flags.append("patch_strategy=DONE")
        parts.append(_block("Patch strategy (ready for PatchAuthor)", str(patch_plan)[:2000]))
    else:
        phase_flags.append("patch_strategy=PENDING")
    patch = str(context.get("patch_diff", ""))
    if patch.strip() and not patch.startswith("# No"):
        parts.append(_block("Current patch (excerpt)", patch[:2500]))
    review = context.get("last_patch_review")
    if isinstance(review, dict):
        parts.append(
            _block(
                "Last patch review",
                f"decision={review.get('decision')} confidence={review.get('confidence')}",
            )
        )
    patch_approved = context.get('patch_approved', False)
    if patch_approved:
        phase_flags.append("patch=APPROVED")
    elif is_material_patch(str(context.get("pending_patch_diff", ""))):
        phase_flags.append("patch=PENDING_REVIEW")
    elif context.get("patch_retry_count", 0) > 0:
        phase_flags.append("patch=IN_PROGRESS")
    else:
        phase_flags.append("patch=NOT_STARTED")

    parts.insert(1, _block("Phase status", " | ".join(phase_flags)))

    parts.append(
        _block(
            "Run flags",
            "\n".join(
                [
                    f"patch_approved={patch_approved}",
                    f"patch_retries={context.get('patch_retry_count', 0)}",
                    f"test_repair_round={context.get('test_repair_attempt', 0)}",
                    f"patch_strategist_used={context.get('patch_strategist_spent', 0)}",
                    f"conductor_steps={context.get('conductor_step', 0)}",
                ]
            ),
        )
    )
    return "\n".join(p for p in parts if p)


def enrich_subagent_context(context: dict[str, Any]) -> dict[str, Any]:
    """Shared briefing injected into every specialist agent call."""
    ctx = dict(context)
    sections: list[str] = [_block("GitHub issue", str(context.get("issue_text", ""))[:4000])]
    analysis = context.get("analysis")
    if isinstance(analysis, dict):
        sections.append(_block("Analyst notes", str(analysis.get("analysis", ""))[:2500]))
        hy = analysis.get("hypotheses")
        if isinstance(hy, list) and hy:
            sections.append(_block("Hypotheses", "\n".join(f"- {x}" for x in hy[:10])))
        rs = analysis.get("repro_steps")
        if isinstance(rs, list) and rs:
            sections.append(_block("Repro steps", "\n".join(f"- {x}" for x in rs[:10])))
        ebc = analysis.get("expected_behavior_changes")
        if isinstance(ebc, list) and ebc:
            sections.append(
                _block(
                    "Expected behavior changes (issue scope)",
                    "\n".join(f"- {x}" for x in ebc[:8]),
                )
            )
    scout = context.get("scout")
    if isinstance(scout, dict):
        notes = scout.get("scout_notes")
        if isinstance(notes, str) and notes.strip():
            sections.append(_block("Code explorer", notes[:2000]))
        target_labels = scout.get("target_test_labels")
        if isinstance(target_labels, list) and target_labels:
            sections.append(
                _block(
                    "Issue-scoped target tests",
                    "Only the following tests verify this specific issue. Do not modify "
                    "code paths whose only purpose is to fix unrelated failing tests.\n"
                    + "\n".join(f"- {label}" for label in target_labels[:8]),
                )
            )
    comparison = context.get("test_comparison")
    if isinstance(comparison, dict) and not comparison.get("scope_clean", True):
        sections.append(
            _block(
                "Scope warning",
                "Latest patch fixed out-of-scope failures: "
                + ", ".join(str(x) for x in comparison.get("unsolicited_fixes", [])[:8])
                + ".",
            )
        )
    ctx["agent_brief"] = "\n".join(s for s in sections if s)
    return ctx
