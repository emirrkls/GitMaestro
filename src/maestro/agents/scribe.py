from __future__ import annotations

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value


_FEEDBACK_MARKER_PREFIX = "<!-- gitmaestro:"


def _idempotency_marker(*, task_id: str, reason: str) -> str:
    """HTML-comment marker the GitHub provider scans for to avoid duplicate comments."""
    return f"{_FEEDBACK_MARKER_PREFIX}run-id={task_id} reason={reason} -->"


def _already_resolved_report(
    *,
    issue_ref: str,
    issue_text: str,
    task_id: str,
    target_labels: list[str],
    baseline: dict[str, object],
) -> tuple[str, str]:
    """Build the markdown report and matching issue comment body.

    The two strings share their content but the comment body wraps the marker
    HTML comment so the provider can detect retries.
    """
    issue_excerpt = issue_text.strip()
    if len(issue_excerpt) > 600:
        issue_excerpt = issue_excerpt[:600].rstrip() + "…"

    bullet_targets = "\n".join(f"- `{label}`" for label in target_labels[:6]) or "- (none reported)"
    baseline_command = str(baseline.get("command") or "N/A")
    baseline_exit = baseline.get("exit_code", "N/A")

    body_lines = [
        f"## GitMaestro feedback: issue already resolved",
        "",
        f"The automation ran a baseline test pass for issue `{issue_ref}` and the",
        "tests that Scout selected as the issue's scope all **already pass**. No patch",
        "was generated.",
        "",
        "### Target tests verified green in baseline",
        bullet_targets,
        "",
        "### Baseline run",
        f"- Command: `{baseline_command}`",
        f"- Exit code: `{baseline_exit}`",
        f"- Passed: `{bool(baseline.get('passed'))}`",
        "",
        "### Likely cause",
        "Another commit or PR on the default branch fixed this issue before",
        "GitMaestro ran. Closing or linking this issue to the resolving PR is",
        "recommended.",
        "",
        "### Issue excerpt",
        "",
        "> " + issue_excerpt.replace("\n", "\n> "),
    ]
    markdown = "\n".join(body_lines)

    marker = _idempotency_marker(task_id=task_id, reason="already_resolved")
    comment_body = f"{marker}\n\n{markdown}"
    return markdown, comment_body


class ReleaseScribeAgent(BaseAgent):
    name = "ReleaseScribe"

    def run(self, context: dict[str, object]) -> AgentResult:
        scribe_task = str(context.get("scribe_task", "draft_commit_and_pr"))
        if scribe_task == "draft_already_resolved_feedback":
            return self._run_already_resolved(context)
        return self._run_commit_and_pr(context)

    def _run_already_resolved(self, context: dict[str, object]) -> AgentResult:
        issue_ref = str(context.get("issue_ref", "unknown"))
        issue_text = str(context.get("issue_text", ""))
        task_id = str(context.get("task_id", "unknown-run"))
        baseline = context.get("test_baseline")
        baseline_dict: dict[str, object] = baseline if isinstance(baseline, dict) else {}

        targets_ctx = context.get("target_already_resolved_targets")
        target_labels: list[str] = []
        if isinstance(targets_ctx, list) and targets_ctx:
            target_labels = [str(x) for x in targets_ctx if str(x).strip()]
        else:
            scout = context.get("scout") if isinstance(context.get("scout"), dict) else {}
            if isinstance(scout, dict):
                raw = scout.get("target_test_labels")
                if isinstance(raw, list):
                    target_labels = [str(x) for x in raw if str(x).strip()]

        markdown, comment_body = _already_resolved_report(
            issue_ref=issue_ref,
            issue_text=issue_text,
            task_id=task_id,
            target_labels=target_labels,
            baseline=baseline_dict,
        )

        return AgentResult(
            summary="Drafted already-resolved feedback (no patch needed).",
            payload={
                "feedback_kind": "already_resolved",
                "issue_feedback_markdown": markdown,
                "issue_comment_body": comment_body,
                "issue_comment_marker": _idempotency_marker(
                    task_id=task_id, reason="already_resolved"
                ),
                "target_labels": target_labels,
                # Provide empty PR fields so downstream artifact writers keep
                # working without special casing this path.
                "commit_message": f"chore(no-op): {issue_ref} already resolved upstream",
                "pr_body": markdown,
            },
            confidence=0.9,
        )

    def _run_commit_and_pr(self, context: dict[str, object]) -> AgentResult:
        issue_ref = str(context.get("issue_ref", "unknown"))
        issue = str(context.get("issue_text", ""))[:2000]
        tests = context.get("test_result", {})
        test_ok = isinstance(tests, dict) and bool(tests.get("passed"))

        scout = context.get("scout") if isinstance(context.get("scout"), dict) else {}
        target_labels: list[str] = []
        if isinstance(scout, dict):
            raw_targets = scout.get("target_test_labels")
            if isinstance(raw_targets, list):
                target_labels = [str(x) for x in raw_targets if str(x).strip()]

        comparison = context.get("test_comparison")
        unsolicited: list[str] = []
        if isinstance(comparison, dict):
            raw_unsolicited = comparison.get("unsolicited_fixes", [])
            if isinstance(raw_unsolicited, list):
                unsolicited = [str(x) for x in raw_unsolicited if str(x).strip()]

        scope_block = ""
        if target_labels:
            scope_block = (
                "\nIssue-scoped target tests (mention these by name in the PR body):\n- "
                + "\n- ".join(target_labels[:6])
            )
        if unsolicited:
            scope_block += (
                "\n\nScope warning — these failures were ALSO fixed but are NOT this issue's "
                "subject; the PR body must explicitly flag them as out-of-scope and link to "
                "separate issues if known:\n- "
                + "\n- ".join(unsolicited[:6])
            )

        prompt = (
            "Write a concise Conventional Commit title and markdown PR body for this fix.\n"
            'Return JSON only: {"commit_message":"...", "pr_body_markdown":"..."}\n'
            "Keep scope tight: the PR addresses one issue only. If a scope warning is given "
            "below, the PR body MUST contain a 'Scope Notes' section that lists the unrelated "
            "fixes and recommends moving them to dedicated PRs/issues. Reference target tests "
            "explicitly.\n\n"
            f"Issue:{issue}\nTesterPassed:{test_ok}{scope_block}"
        )
        response = self.llm.complete(model=self.model, prompt=prompt)
        parsed = extract_first_json_value(response.text)

        commit_message = f"fix(issue): address {issue_ref} with scoped patch"
        pr_body_lines = [
            "## Summary",
            "- Minimal patch produced after analyst/scout-guided review.",
            f"- Tester signal: {'pass' if test_ok else 'fail or unknown'}.",
            "",
            "## Test Plan",
            "- Run repository test discovery command recorded by Tester.",
        ]
        if target_labels:
            pr_body_lines.extend(
                [
                    "",
                    "## Targeted Tests",
                    *(f"- `{label}`" for label in target_labels[:6]),
                ]
            )
        if unsolicited:
            pr_body_lines.extend(
                [
                    "",
                    "## Scope Notes",
                    "The following baseline failures went green but are unrelated to this "
                    "issue. They should be tracked as separate issues:",
                    *(f"- `{label}`" for label in unsolicited[:6]),
                ]
            )
        pr_body_lines.extend(
            [
                "",
                "## Risk",
                "- Scoped change; monitor related modules for regressions.",
            ]
        )
        pr_body = "\n".join(pr_body_lines)

        if isinstance(parsed, dict):
            cm = parsed.get("commit_message")
            if isinstance(cm, str) and cm.strip():
                commit_message = cm.strip().splitlines()[0][:120]
            pb = parsed.get("pr_body_markdown") or parsed.get("pr_body")
            if isinstance(pb, str) and pb.strip():
                pr_body = pb.strip()

        return AgentResult(
            summary="Commit message and PR draft prepared.",
            payload={"commit_message": commit_message, "pr_body": pr_body},
            confidence=0.76,
        )


ScribeAgent = ReleaseScribeAgent
