from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from maestro.agents.analyst import AnalystAgent
from maestro.agents.critic import CriticAgent
from maestro.agents.maestro_agent import MaestroAgent
from maestro.agents.scout import ScoutAgent
from maestro.agents.scribe import ScribeAgent
from maestro.agents.surgeon import SurgeonAgent
from maestro.agents.tester import TesterAgent
from maestro.config.model_routing import ModelRouter
from maestro.config.settings import AppConfig
from maestro.core.ad_hoc_factory import AdHocAgentSpec, AdHocFactory
from maestro.core.logger import EventLogger
from maestro.core.message import OrchestrationEvent, new_correlation_id
from maestro.core.score import build_initial_score
from maestro.core.state import RunState
from maestro.policies.retry import should_retry
from maestro.policies.safety import evaluate_safety_gate
from maestro.providers.git_ops import GitOpsProvider
from maestro.providers.github import GitHubProvider
from maestro.providers.llm.factory import build_llm_provider
from maestro.providers.test_runner import TestRunner


class MaestroOrchestrator:
    def __init__(self, repo_path: Path, config: AppConfig) -> None:
        self.repo_path = repo_path
        self.config = config
        self.model_router = ModelRouter(config.models)
        self.llm = build_llm_provider(mock_llm=config.runtime.mock_llm)
        self.github = GitHubProvider(repo_path=repo_path, enabled=config.runtime.github_enabled)
        self.git_ops = GitOpsProvider(repo_path=repo_path)

    def run(self, repo_ref: str, issue_ref: str) -> RunState:
        task_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + str(uuid4())[:8]
        run_dir = self.repo_path / "runs" / task_id
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
                "repo_path": str(self.repo_path),
                "complexity": score.complexity,
                "issue_url": issue.url,
                "issue_number": issue.number,
                "llm_provider": type(self.llm).__name__,
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

        maestro = MaestroAgent(self.llm, self.model_router.model_for("Maestro"))
        analyst = AnalystAgent(self.llm, self.model_router.model_for("Analyst"))
        scout = ScoutAgent(self.llm, self.model_router.model_for("Scout"))
        surgeon = SurgeonAgent(self.llm, self.model_router.model_for("Surgeon"))
        critic = CriticAgent(self.llm, self.model_router.model_for("Critic"))
        test_runner = TestRunner(
            repo_path=self.repo_path,
            allowed_prefixes=self.config.runtime.test_command_allowlist,
            timeout_seconds=self.config.runtime.test_timeout_seconds,
        )
        tester = TesterAgent(self.llm, self.model_router.model_for("Tester"), test_runner=test_runner)
        scribe = ScribeAgent(self.llm, self.model_router.model_for("Scribe"))

        self._dispatch(logger, state, "Maestro", "Maestro", "task", {"task": "triage"})
        maestro_result = maestro.run(state.context)
        self._dispatch(logger, state, "Maestro", "Maestro", "result", maestro_result.payload, maestro_result.confidence)
        state.decision_trace.append(f"Maestro triage: {maestro_result.payload['triage_decision']}")

        self._dispatch(logger, state, "Maestro", "Analyst", "task", {"task": "decompose_issue"})
        analyst_result = analyst.run(state.context)
        state.context["analysis"] = analyst_result.payload
        self._dispatch(logger, state, "Analyst", "Maestro", "result", analyst_result.payload, analyst_result.confidence)
        state.decision_trace.append(analyst_result.summary)

        self._dispatch(logger, state, "Maestro", "Scout", "task", {"task": "discover_code_context"})
        scout_result = scout.run(state.context)
        state.context["scout"] = scout_result.payload
        self._dispatch(logger, state, "Scout", "Maestro", "result", scout_result.payload, scout_result.confidence)
        state.decision_trace.append(scout_result.summary)
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
            final_decision = "human_escalation"
            latest_patch = ""
            logger.write_json("score.json", score.to_dict())
            logger.write_artifact("decision_trace.md", "\n".join(f"- {line}" for line in state.decision_trace))
            logger.write_artifact("patch.diff", "# No patch generated due to escalation\n")
            logger.write_artifact("test_report.md", "# Test Report\nSkipped due to escalation.\n")
            logger.write_artifact("pr_draft.md", "# PR Draft\n\nSkipped due to escalation.\n")
            logger.write_artifact("commit_message.txt", "chore: escalated ambiguous issue for human clarification")
            self._dispatch(
                logger,
                state,
                "Maestro",
                "System",
                "decision",
                {"final_decision": final_decision, "next": "await_human_input"},
                confidence=0.86,
            )
            return state

        retry_count = 0
        approved = False
        latest_patch = ""
        latest_critic_feedback: list[str] = []
        while True:
            state.context["retry_count"] = retry_count
            self._dispatch(logger, state, "Maestro", "Surgeon", "task", {"task": "minimal_patch", "retry": retry_count})
            surgeon_result = surgeon.run(state.context)
            latest_patch = str(surgeon_result.payload.get("patch_diff", ""))
            self._dispatch(
                logger,
                state,
                "Surgeon",
                "Maestro",
                "result",
                surgeon_result.payload,
                surgeon_result.confidence,
            )

            critic_context = dict(state.context)
            critic_context["patch_diff"] = latest_patch
            critic_context["retry_count"] = retry_count
            self._dispatch(logger, state, "Maestro", "Critic", "task", {"task": "review_patch", "retry": retry_count})
            critic_result = critic.run(critic_context)
            self._dispatch(logger, state, "Critic", "Maestro", "feedback", critic_result.payload, critic_result.confidence)
            decision = str(critic_result.payload.get("decision", "reject"))
            latest_critic_feedback = list(critic_result.payload.get("feedback", []))
            state.decision_trace.append(f"Critic decision retry={retry_count}: {decision}")
            if decision == "approve":
                approved = True
                break
            if should_retry(
                critic_decision=decision,
                retry_count=retry_count,
                max_retries=self.config.runtime.max_retries,
            ):
                retry_count += 1
                continue
            break

        if not approved:
            self._dispatch(
                logger,
                state,
                "Maestro",
                "Human",
                "escalation",
                {"reason": "critic_reject_retry_exhausted", "retry_count": retry_count},
                confidence=0.84,
                blocking_reason="max_retry_exhausted",
            )
            state.decision_trace.append("Escalated to human due to critic rejection loop.")
            final_decision = "human_escalation"
        else:
            state.context["patch_diff"] = latest_patch
            state.context["critic_feedback"] = latest_critic_feedback
            state.context["test_command"] = "python -m unittest discover"
            self._dispatch(logger, state, "Maestro", "Tester", "task", {"task": "execute_tests"})
            tester_result = tester.run(state.context)
            self._dispatch(logger, state, "Tester", "Maestro", "result", tester_result.payload, tester_result.confidence)
            state.context["test_result"] = tester_result.payload
            state.decision_trace.append(f"Tester passed={tester_result.payload.get('passed')}")

            safety = evaluate_safety_gate(state.context)
            self._dispatch(
                logger,
                state,
                "Maestro",
                "SafetyGate",
                "decision",
                safety,
                confidence=0.79,
                blocking_reason=str(safety.get("reason")) if not safety.get("passed") else None,
            )
            if not safety.get("passed", False):
                final_decision = "reject"
                state.decision_trace.append(f"Safety gate blocked: {safety.get('reason')}")
            elif not tester_result.payload.get("passed", False):
                final_decision = "reject"
                state.decision_trace.append("Rejected due to failed tests.")
            else:
                self._dispatch(logger, state, "Maestro", "Scribe", "task", {"task": "draft_commit_and_pr"})
                scribe_context = dict(state.context)
                scribe_context["issue_ref"] = issue_ref
                scribe_result = scribe.run(scribe_context)
                self._dispatch(
                    logger,
                    state,
                    "Scribe",
                    "Maestro",
                    "result",
                    scribe_result.payload,
                    scribe_result.confidence,
                )
                state.context["scribe"] = scribe_result.payload
                final_decision = "commit_ready"
                state.decision_trace.append("Ready for commit/PR draft.")
                gh_summary = self._handle_github_finalize(
                    repo_ref=repo_ref,
                    issue_number=str(issue.number),
                    scribe_payload=scribe_result.payload,
                )
                state.context["github_finalize"] = gh_summary
                state.decision_trace.append(gh_summary)

        if score.complexity == "high" and score.ad_hoc_budget > 0:
            ad_hoc_spec = AdHocAgentSpec(
                agent_name="SecurityPatchAdvisor",
                creation_reason="High-complexity signal detected",
                role_spec="Inspect potential security side-effects in touched modules",
            )
            ad_hoc_factory.create(ad_hoc_spec)
            self._dispatch(
                logger,
                state,
                "Maestro",
                "SecurityPatchAdvisor",
                "task",
                {"task": "targeted_investigation", "scope": "read-only"},
            )
            ad_hoc_factory.close(ad_hoc_spec, close_reason="single-task-completed")
            state.decision_trace.append("Ad-hoc agent created and closed within issue scope.")

        logger.write_json("score.json", score.to_dict())
        logger.write_artifact("llm_provider.txt", str(state.context.get("llm_provider", "unknown")))
        logger.write_artifact(
            "issue_snapshot.md",
            "\n".join(
                [
                    "# Issue Snapshot",
                    f"- Repo: {repo_ref}",
                    f"- Number: {issue.number}",
                    f"- URL: {issue.url}",
                    "",
                    "## Title",
                    issue.title,
                    "",
                    "## Body",
                    issue.body[:4000],
                ]
            ),
        )
        logger.write_artifact("decision_trace.md", "\n".join(f"- {line}" for line in state.decision_trace))
        logger.write_artifact("patch.diff", latest_patch or "# No patch generated\n")
        test_payload = state.context.get("test_result", {})
        logger.write_artifact(
            "test_report.md",
            "\n".join(
                [
                    "# Test Report",
                    f"- Passed: {test_payload.get('passed', False)}",
                    f"- Command: {test_payload.get('command', 'N/A')}",
                    f"- Exit Code: {test_payload.get('exit_code', 'N/A')}",
                    "",
                    "## stderr",
                    str(test_payload.get("stderr", ""))[:2000],
                ]
            ),
        )
        scribe_payload = state.context.get("scribe", {})
        logger.write_artifact(
            "pr_draft.md",
            str(scribe_payload.get("pr_body", "# PR Draft\n\nNot available.\n")),
        )
        logger.write_artifact(
            "commit_message.txt",
            str(scribe_payload.get("commit_message", "chore: pending scribe")),
        )
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

    def _handle_github_finalize(
        self,
        repo_ref: str,
        issue_number: str,
        scribe_payload: dict[str, object],
    ) -> str:
        if not self.config.runtime.github_enabled:
            return "GitHub finalize disabled by config."
        if not self.git_ops.is_git_repo():
            return "GitHub finalize skipped: current directory is not a git repository."
        if not self.github.is_gh_available():
            return "GitHub finalize skipped: `gh` CLI is not installed."
        branch = f"{self.config.runtime.branch_prefix}-{issue_number}"
        branch_log = self.git_ops.ensure_branch(branch)
        if not self.config.runtime.allow_commit:
            return f"Branch prepared: {branch}. Commit disabled by config. {branch_log}"

        commit_message = str(scribe_payload.get("commit_message", f"fix: resolve issue {issue_number}"))
        commit_log = self.git_ops.commit_if_changes(commit_message)
        if not self.config.runtime.allow_push:
            return f"Branch prepared: {branch}. Commit result: {commit_log}. Push disabled by config."

        push_log = self.git_ops.push_branch(branch)
        if not self.config.runtime.allow_pr_draft:
            return f"Branch pushed: {push_log}. PR draft disabled by config."

        pr_title = commit_message
        pr_body = str(scribe_payload.get("pr_body", ""))
        pr_log = self.github.create_draft_pr(repo=repo_ref, title=pr_title, body=pr_body, branch=branch)
        return f"GitHub finalize complete. Branch={branch}. Push={push_log}. PR={pr_log}"

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
