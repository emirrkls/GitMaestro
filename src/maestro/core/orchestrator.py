from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from maestro.config.model_routing import ModelRouter
from maestro.config.settings import AppConfig
from maestro.core.ad_hoc_factory import AdHocFactory
from maestro.core.conductor_loop import ConductorLoop
from maestro.core.logger import EventLogger
from maestro.core.message import OrchestrationEvent, new_correlation_id
from maestro.core.score import build_initial_score
from maestro.core.state import RunState
from maestro.providers.git_ops import GitOpsProvider
from maestro.providers.github import GitHubProvider
from maestro.providers.llm.factory import build_llm_provider
from maestro.providers.test_runner import TestRunner


class MaestroOrchestrator:
    def __init__(self, repo_path: Path, config: AppConfig) -> None:
        self.repo_path = repo_path
        self.config = config
        self.model_router = ModelRouter(config.models)
        self.llm = build_llm_provider(config.runtime)
        self.github = GitHubProvider(repo_path=repo_path, enabled=config.runtime.github_enabled)
        self.git_ops = GitOpsProvider(repo_path=repo_path)

    def run(self, repo_ref: str, issue_ref: str) -> RunState:
        task_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + str(uuid4())[:8]
        run_dir = self.repo_path / "runs" / task_id
        workspace_path = self._prepare_workspace(repo_ref=repo_ref, run_dir=run_dir)
        run_git_ops = GitOpsProvider(repo_path=workspace_path)
        issue = self.github.fetch_issue(repo_ref, issue_ref)
        issue_text = f"{issue.title}\n\n{issue.body}".strip()
        score = build_initial_score(
            issue_text=issue_text,
            ad_hoc_budget=self.config.runtime.ad_hoc_budget,
            max_retries=self.config.runtime.max_retries,
        )
        state = RunState(
            task_id=task_id,
            repo=repo_ref,
            issue_ref=issue_ref,
            run_dir=run_dir,
            score=score,
            context={
                "issue_text": issue_text,
                "repo_path": str(workspace_path),
                "complexity": score.complexity,
                "issue_url": issue.url,
                "issue_number": issue.number,
                "llm_provider": type(self.llm).__name__,
                "workspace_path": str(workspace_path),
            },
        )
        logger = EventLogger(run_dir)
        ad_hoc_factory = AdHocFactory(logger=logger, task_id=task_id)
        if hasattr(self.llm, "set_telemetry_sink"):
            self.llm.set_telemetry_sink(  # type: ignore[union-attr]
                lambda event_name, payload: self._dispatch(
                    logger,
                    state,
                    "LLMRouter",
                    "Maestro",
                    "feedback",
                    {"telemetry": event_name, **payload},
                )
            )

        if score.complexity == "ambiguous":
            self._dispatch(
                logger,
                state,
                "Maestro",
                "Human",
                "escalation",
                {"reason": "ambiguous_issue_requires_clarification"},
                confidence=0.86,
                blocking_reason="insufficient_issue_detail",
            )
            state.decision_trace.append("Escalated early due to ambiguous issue details.")
            return self._finalize_run(
                state=state,
                logger=logger,
                issue=issue,
                repo_ref=repo_ref,
                workspace_path=workspace_path,
                final_decision="human_escalation",
                run_git_ops=run_git_ops,
            )

        test_runner = TestRunner(
            repo_path=workspace_path,
            allowed_prefixes=self.config.runtime.test_command_allowlist,
            timeout_seconds=self.config.runtime.test_timeout_seconds,
        )
        loop = ConductorLoop(
            config=self.config,
            llm=self.llm,
            model_router=self.model_router,
            logger=logger,
            state=state,
            ad_hoc_factory=ad_hoc_factory,
            test_runner=test_runner,
            issue_ref=issue_ref,
        )
        final_decision = loop.run()

        if final_decision == "commit_ready":
            gh_summary = self._handle_github_finalize(
                git_ops=run_git_ops,
                repo_ref=repo_ref,
                issue_number=str(issue.number),
                scribe_payload=state.context.get("scribe", {}),
            )
            state.context["github_finalize"] = gh_summary
            state.decision_trace.append(gh_summary)
        elif final_decision == "already_resolved":
            comment_log = self._post_issue_feedback_comment(
                repo_ref=repo_ref,
                issue_number=str(issue.number),
                scribe_payload=state.context.get("scribe", {}),
            )
            state.context["github_finalize"] = comment_log
            state.decision_trace.append(comment_log)

        return self._finalize_run(
            state=state,
            logger=logger,
            issue=issue,
            repo_ref=repo_ref,
            workspace_path=workspace_path,
            final_decision=final_decision,
            run_git_ops=run_git_ops,
        )

    def _finalize_run(
        self,
        *,
        state: RunState,
        logger: EventLogger,
        issue: object,
        repo_ref: str,
        workspace_path: Path,
        final_decision: str,
        run_git_ops: GitOpsProvider,
    ) -> RunState:
        logger.write_json("score.json", state.score.to_dict())
        logger.write_artifact("llm_provider.txt", str(state.context.get("llm_provider", "unknown")))
        logger.write_artifact(
            "issue_snapshot.md",
            "\n".join(
                [
                    "# Issue Snapshot",
                    f"- Repo: {repo_ref}",
                    f"- Number: {getattr(issue, 'number', '')}",
                    f"- URL: {getattr(issue, 'url', '')}",
                    "",
                    "## Title",
                    str(getattr(issue, "title", "")),
                    "",
                    "## Body",
                    str(getattr(issue, "body", ""))[:4000],
                ]
            ),
        )
        logger.write_artifact("decision_trace.md", "\n".join(f"- {line}" for line in state.decision_trace))
        workspace_diff = self._collect_workspace_diff(workspace_path)
        patch_fallback = str(state.context.get("patch_diff", ""))
        logger.write_artifact("patch.diff", workspace_diff or patch_fallback or "# No patch generated\n")

        test_payload = state.context.get("test_result", {})
        baseline_payload = state.context.get("test_baseline")
        report_md_parts: list[str] = ["# Test Report", ""]
        if isinstance(baseline_payload, dict):
            report_md_parts.extend(
                [
                    "## Pre-patch baseline",
                    f"- Passed: {baseline_payload.get('passed', False)}",
                    f"- Command: {baseline_payload.get('command', 'N/A')}",
                    f"- Exit Code: {baseline_payload.get('exit_code', 'N/A')}",
                    "",
                    "### stderr (baseline)",
                    str(baseline_payload.get("stderr", ""))[:4000],
                    "",
                    "---",
                    "",
                ]
            )
        if isinstance(test_payload, dict):
            report_md_parts.extend(
                [
                    "## Final test run (post-patch)",
                    f"- Passed: {test_payload.get('passed', False)}",
                    f"- Command: {test_payload.get('command', 'N/A')}",
                    f"- Exit Code: {test_payload.get('exit_code', 'N/A')}",
                    "",
                    "### stderr (final)",
                    str(test_payload.get("stderr", ""))[:4000],
                ]
            )
        logger.write_artifact("test_report.md", "\n".join(report_md_parts))

        scribe_payload = state.context.get("scribe", {})
        if isinstance(scribe_payload, dict):
            logger.write_artifact(
                "pr_draft.md",
                str(scribe_payload.get("pr_body", "# PR Draft\n\nNot available.\n")),
            )
            logger.write_artifact(
                "commit_message.txt",
                str(scribe_payload.get("commit_message", "chore: pending scribe")),
            )
            feedback_md = scribe_payload.get("issue_feedback_markdown")
            if isinstance(feedback_md, str) and feedback_md.strip():
                logger.write_artifact("issue_feedback.md", feedback_md)
        else:
            logger.write_artifact("pr_draft.md", "# PR Draft\n\nSkipped.\n")
            logger.write_artifact("commit_message.txt", "chore: no scribe output")

        logger.write_artifact(
            "github_summary.md",
            str(state.context.get("github_finalize", "GitHub finalize step skipped.")),
        )
        self._dispatch(
            logger,
            state,
            "Maestro",
            "System",
            "decision",
            {"final_decision": final_decision, "next": "ready_for_next_stage"},
            confidence=0.81,
        )
        return state

    def _post_issue_feedback_comment(
        self,
        *,
        repo_ref: str,
        issue_number: str,
        scribe_payload: object,
    ) -> str:
        if not isinstance(scribe_payload, dict):
            return "Issue feedback comment skipped: no scribe payload."
        comment_body = scribe_payload.get("issue_comment_body")
        if not isinstance(comment_body, str) or not comment_body.strip():
            return "Issue feedback comment skipped: scribe produced no comment body."
        if not self.config.runtime.post_issue_feedback_comments:
            return (
                "Issue feedback report written to runs/<task_id>/issue_feedback.md. "
                "Set runtime.post_issue_feedback_comments=true to also post it on the issue."
            )
        marker_raw = scribe_payload.get("issue_comment_marker")
        marker = marker_raw if isinstance(marker_raw, str) and marker_raw.strip() else None
        return self.github.post_issue_comment(
            repo=repo_ref,
            issue_number=issue_number,
            body=comment_body,
            idempotency_marker=marker,
        )

    def _handle_github_finalize(
        self,
        git_ops: GitOpsProvider,
        repo_ref: str,
        issue_number: str,
        scribe_payload: dict[str, object],
    ) -> str:
        if not self.config.runtime.github_enabled:
            return "GitHub finalize disabled by config."
        if not git_ops.is_git_repo():
            return "GitHub finalize skipped: current directory is not a git repository."
        branch = f"{self.config.runtime.branch_prefix}-{issue_number}"
        branch_log = git_ops.ensure_branch(branch)
        if not self.config.runtime.allow_commit:
            return f"Branch prepared: {branch}. Commit disabled by config. {branch_log}"

        commit_message = str(scribe_payload.get("commit_message", f"fix: resolve issue {issue_number}"))
        commit_log = git_ops.commit_if_changes(commit_message)
        if not self.config.runtime.allow_push:
            return f"Branch prepared: {branch}. Commit result: {commit_log}. Push disabled by config."

        push_log = git_ops.push_branch(branch)
        if not self.config.runtime.allow_pr_draft:
            return f"Branch pushed: {push_log}. PR draft disabled by config."

        pr_title = commit_message
        pr_body = str(scribe_payload.get("pr_body", ""))
        pr_log = self.github.create_draft_pr(repo=repo_ref, title=pr_title, body=pr_body, branch=branch)
        return f"GitHub finalize complete. Branch={branch}. Push={push_log}. PR={pr_log}"

    def _prepare_workspace(self, repo_ref: str, run_dir: Path) -> Path:
        workspace = run_dir / "workspace"
        clone_url = f"https://github.com/{repo_ref}.git"
        completed = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(workspace)],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        if completed.returncode != 0:
            return self.repo_path
        return workspace

    def _collect_workspace_diff(self, workspace_path: Path) -> str:
        completed = subprocess.run(
            ["git", "diff"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        if completed.returncode != 0:
            return ""
        return completed.stdout

    def _dispatch(
        self,
        logger: EventLogger,
        state: RunState,
        sender: str,
        receiver: str,
        event_type: str,
        content: dict[str, object],
        confidence: float | None = None,
        blocking_reason: str | None = None,
    ) -> None:
        logger.log_event(
            OrchestrationEvent(
                task_id=state.task_id,
                correlation_id=new_correlation_id(),
                sender=sender,
                receiver=receiver,
                type=event_type,  # type: ignore[arg-type]
                content=content,
                confidence=confidence,
                blocking_reason=blocking_reason,
            )
        )
