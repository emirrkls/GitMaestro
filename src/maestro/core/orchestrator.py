from __future__ import annotations

import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from maestro.agents.analyst import AnalystAgent
from maestro.agents.critic import CriticAgent
from maestro.agents.maestro_agent import MaestroAgent
from maestro.agents.scout import ScoutAgent
from maestro.agents.patch_planner import PatchPlannerAgent
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
from maestro.policies.ad_hoc_trigger import (
    should_precall_patch_planner,
    should_spawn_patch_planner_on_surgeon_miss,
)
from maestro.policies.patch_signals import is_material_unified_diff
from maestro.policies.patch_strategy import classify_change_scale
from maestro.policies.retry import should_retry
from maestro.policies.safety import evaluate_safety_gate
from maestro.policies.test_feedback import (
    build_test_repair_feedback,
    compare_test_results,
    test_focus_files_for_context,
)
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

        maestro = MaestroAgent(self.llm, self.model_router.model_for("Maestro"))
        analyst = AnalystAgent(self.llm, self.model_router.model_for("Analyst"))
        scout = ScoutAgent(self.llm, self.model_router.model_for("Scout"))
        surgeon = SurgeonAgent(self.llm, self.model_router.model_for("Surgeon"))
        critic = CriticAgent(self.llm, self.model_router.model_for("Critic"))
        test_runner = TestRunner(
            repo_path=workspace_path,
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

        if self.config.runtime.test_baseline_before_patch:
            self._dispatch(logger, state, "Maestro", "Tester", "task", {"task": "execute_tests_baseline"})
            baseline_result = tester.run(state.context)
            state.context["test_baseline"] = baseline_result.payload
            self._dispatch(
                logger,
                state,
                "Tester",
                "Maestro",
                "result",
                baseline_result.payload,
                baseline_result.confidence,
            )
            bp = baseline_result.payload
            state.decision_trace.append(
                f"Test baseline (pre-patch): passed={bp.get('passed')} command={bp.get('command')!r}"
            )
            if not bp.get("passed"):
                state.context["baseline_test_feedback"] = (
                    "Pre-patch test run (issue workspace before Surgeon edits).\n\n"
                    + str(bp.get("stderr") or "")[:4500]
                )
            else:
                state.context.pop("baseline_test_feedback", None)

        change_scale = classify_change_scale(state.context)
        state.context["change_scale"] = change_scale
        state.context["strategy_max_diff_lines"] = self.config.runtime.patch_strategy_max_diff_lines
        state.context["strategy_max_diff_bytes"] = self.config.runtime.patch_strategy_max_diff_bytes
        state.context["rewrite_enabled"] = self.config.runtime.patch_strategy_rewrite_enabled
        state.context["hunk_enabled"] = self.config.runtime.patch_strategy_hunk_enabled
        state.context["snippet_enabled"] = self.config.runtime.patch_strategy_snippet_enabled
        state.decision_trace.append(f"Patch change scale classified as: {change_scale}")

        retry_count = 0
        approved = False
        latest_patch = ""
        latest_critic_feedback: list[str] = []
        any_material_patch = False
        ad_hoc_spent = 0
        material_prev = False
        human_escalation_reason = "critic_reject_retry_exhausted"
        state.context["mock_llm"] = self.config.runtime.mock_llm
        seen_patch_fingerprints: set[str] = set()
        repeated_patch_attempts = 0

        while True:
            state.context["retry_count"] = retry_count
            planner_room = ad_hoc_spent < score.ad_hoc_budget
            pre_ready = planner_room and retry_count == 0 and should_precall_patch_planner(
                workspace_path, score
            )
            post_ready = planner_room and should_spawn_patch_planner_on_surgeon_miss(
                surgeon_had_material_patch=material_prev,
                retry_count=retry_count,
                ad_hoc_budget=score.ad_hoc_budget,
                ad_hoc_spent=ad_hoc_spent,
            )
            if pre_ready or post_ready:
                spec = AdHocAgentSpec(
                    agent_name="PatchPlanner",
                    creation_reason="Structured patch decomposition before Surgeon executes",
                    role_spec="Produce JSON snippet edits constrained to scout-ranked files.",
                    tool_scope="read-only",
                    ttl="single-invocation",
                )
                ad_hoc_factory.create(spec)
                planner = PatchPlannerAgent(self.llm, self.model_router.model_for("PatchPlanner"))
                planner_result = planner.run(state.context)
                ad_hoc_factory.close(spec, close_reason="patch_plan_queued_for_surgeon")
                plan = planner_result.payload.get("patch_plan")
                if isinstance(plan, dict):
                    state.context["patch_plan"] = plan
                self._dispatch(
                    logger,
                    state,
                    "PatchPlanner",
                    "Maestro",
                    "result",
                    planner_result.payload,
                    planner_result.confidence,
                )
                ad_hoc_spent += 1
                state.decision_trace.append(
                    f"PatchPlanner spawned ({'precall' if pre_ready else 'retry_assist'}) [{ad_hoc_spent}/{score.ad_hoc_budget}]."
                )

            self._dispatch(logger, state, "Maestro", "Surgeon", "task", {"task": "minimal_patch", "retry": retry_count})
            surgeon_result = surgeon.run(state.context)
            state.context.pop("patch_plan", None)

            candidate_patch = str(surgeon_result.payload.get("patch_diff", ""))
            patch_material = is_material_unified_diff(candidate_patch)
            if patch_material:
                latest_patch = candidate_patch
                any_material_patch = True
            material_prev = patch_material
            self._dispatch(
                logger,
                state,
                "Surgeon",
                "Maestro",
                "result",
                surgeon_result.payload,
                surgeon_result.confidence,
            )
            strategy_used = surgeon_result.payload.get("strategy_used")
            if strategy_used:
                state.decision_trace.append(
                    f"Surgeon strategy retry={retry_count}: {strategy_used} ({surgeon_result.payload.get('surgeon_status')})"
                )
            fallback_reason = surgeon_result.payload.get("fallback_reason")
            if fallback_reason:
                state.decision_trace.append(f"Surgeon fallback note retry={retry_count}: {fallback_reason}")

            status = str(surgeon_result.payload.get("surgeon_status") or "")
            attempts = str(surgeon_result.payload.get("strategy_attempts") or "")
            fp_input = f"{status}|{attempts}"
            fp = hashlib.sha1(fp_input.encode("utf-8")).hexdigest()
            if fp in seen_patch_fingerprints:
                repeated_patch_attempts += 1
            else:
                seen_patch_fingerprints.add(fp)
                repeated_patch_attempts = 0

            if not patch_material:
                if repeated_patch_attempts >= 2:
                    state.decision_trace.append(
                        f"Stopping repeated Surgeon retries at retry={retry_count}: repeated_non_material_attempts"
                    )
                    human_escalation_reason = "surgeon_repeated_non_material_attempts"
                    break
                state.decision_trace.append(
                    f"No material unified diff (retry={retry_count}); skipping Critic for another Surgeon attempt."
                )
                if retry_count < self.config.runtime.max_retries:
                    retry_count += 1
                    continue
                human_escalation_reason = "surgeon_no_material_patch_exhausted"
                break

            critic_context = dict(state.context)
            critic_context["patch_diff"] = candidate_patch
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
            trace_escalation = (
                "Escalated: Surgeon could not produce an applyable material patch within the retry budget."
                if human_escalation_reason == "surgeon_no_material_patch_exhausted"
                else "Escalated to human due to critic rejection retry exhaustion."
            )
            self._dispatch(
                logger,
                state,
                "Maestro",
                "Human",
                "escalation",
                {"reason": human_escalation_reason, "retry_count": retry_count},
                confidence=0.84,
                blocking_reason="max_retry_exhausted",
            )
            state.decision_trace.append(trace_escalation)
            final_decision = "human_escalation"
        else:
            state.context["patch_diff"] = latest_patch
            state.context["critic_feedback"] = latest_critic_feedback

            test_repair_round = 0
            test_passed = False

            while True:
                self._dispatch(logger, state, "Maestro", "Tester", "task", {"task": "execute_tests"})
                tester_result = tester.run(state.context)
                tester_result_payload = tester_result.payload
                self._dispatch(
                    logger,
                    state,
                    "Tester",
                    "Maestro",
                    "result",
                    tester_result.payload,
                    tester_result.confidence,
                )
                state.context["test_result"] = tester_result.payload
                state.decision_trace.append(
                    f"Tester passed={tester_result.payload.get('passed')} (post-patch round={test_repair_round})"
                )

                comparison = compare_test_results(
                    baseline=state.context.get("test_baseline")
                    if isinstance(state.context.get("test_baseline"), dict)
                    else None,
                    post_patch=tester_result.payload,
                )
                state.context["test_comparison"] = comparison
                self._dispatch(
                    logger,
                    state,
                    "TesterPolicy",
                    "Maestro",
                    "feedback",
                    {"test_comparison": comparison},
                    confidence=0.83,
                )
                state.decision_trace.append(f"Test comparison: {comparison.get('summary')}")

                if comparison.get("no_regression"):
                    test_passed = True
                    if comparison.get("baseline_failures"):
                        state.decision_trace.append(
                            "Tests: no regression. "
                            f"{len(comparison['baseline_failures'])} pre-existing failures ignored. "
                            f"{len(comparison.get('fixed_by_patch', []))} bonus fixes."
                        )
                    break

                if test_repair_round >= self.config.runtime.test_repair_max_retries:
                    break

                test_repair_round += 1
                state.context["test_repair_attempt"] = test_repair_round
                stderr_now = str(tester_result.payload.get("stderr") or "")
                state.context["test_failure_feedback"] = build_test_repair_feedback(
                    state.context.get("test_baseline") if isinstance(state.context.get("test_baseline"), dict) else None,
                    tester_result.payload,
                    workspace=workspace_path,
                )
                state.context["test_focus_files"] = test_focus_files_for_context(stderr_now, workspace_path)
                # Keep Scout candidates aligned with latest failing test context so Surgeon
                # digests current relevant files in test-repair retries.
                existing_scout = state.context.get("scout", {})
                if isinstance(existing_scout, dict):
                    existing_candidates = list(existing_scout.get("candidate_files", []))
                    focus = state.context.get("test_focus_files", [])
                    if isinstance(focus, list):
                        for f in focus:
                            if f not in existing_candidates:
                                existing_candidates.append(f)
                    state.context["scout"] = {**existing_scout, "candidate_files": existing_candidates}
                state.decision_trace.append(
                    f"Tests failed; starting repair pass {test_repair_round}/"
                    f"{self.config.runtime.test_repair_max_retries}"
                )

                repair_inner = 0
                repair_approved = False
                while repair_inner <= self.config.runtime.max_retries:
                    state.context["retry_count"] = repair_inner
                    self._dispatch(
                        logger,
                        state,
                        "Maestro",
                        "Surgeon",
                        "task",
                        {"task": "test_repair_patch", "retry": repair_inner},
                    )
                    surgeon_result = surgeon.run(state.context)
                    state.context.pop("patch_plan", None)

                    candidate_patch = str(surgeon_result.payload.get("patch_diff", ""))
                    patch_material = is_material_unified_diff(candidate_patch)
                    if patch_material:
                        latest_patch = candidate_patch
                        any_material_patch = True
                    self._dispatch(
                        logger,
                        state,
                        "Surgeon",
                        "Maestro",
                        "result",
                        surgeon_result.payload,
                        surgeon_result.confidence,
                    )
                    strategy_used = surgeon_result.payload.get("strategy_used")
                    if strategy_used:
                        state.decision_trace.append(
                            "Test repair Surgeon strategy "
                            f"inner={repair_inner}: {strategy_used} ({surgeon_result.payload.get('surgeon_status')})"
                        )

                    if not patch_material:
                        state.decision_trace.append(
                            f"Test repair: no material unified diff (inner={repair_inner})"
                        )
                        if repair_inner < self.config.runtime.max_retries:
                            repair_inner += 1
                            continue
                        break

                    critic_context = dict(state.context)
                    critic_context["patch_diff"] = candidate_patch
                    critic_context["retry_count"] = repair_inner
                    self._dispatch(
                        logger,
                        state,
                        "Maestro",
                        "Critic",
                        "task",
                        {"task": "review_patch", "retry": repair_inner},
                    )
                    critic_result = critic.run(critic_context)
                    self._dispatch(
                        logger,
                        state,
                        "Critic",
                        "Maestro",
                        "feedback",
                        critic_result.payload,
                        critic_result.confidence,
                    )
                    decision = str(critic_result.payload.get("decision", "reject"))
                    latest_critic_feedback = list(critic_result.payload.get("feedback", []))
                    state.decision_trace.append(f"Test-repair Critic inner={repair_inner}: {decision}")

                    if decision == "approve":
                        repair_approved = True
                        state.context["patch_diff"] = latest_patch
                        state.context["critic_feedback"] = latest_critic_feedback
                        break
                    if should_retry(
                        critic_decision=decision,
                        retry_count=repair_inner,
                        max_retries=self.config.runtime.max_retries,
                    ):
                        repair_inner += 1
                        continue
                    break

                if not repair_approved:
                    state.decision_trace.append("Test repair: no approved follow-up patch; stopping repair loop.")
                    break

            state.context.pop("test_failure_feedback", None)
            state.context.pop("test_focus_files", None)
            state.context.pop("test_repair_attempt", None)

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
            elif not any_material_patch:
                final_decision = "reject"
                state.decision_trace.append("Rejected: no material patch was applied to target workspace.")
            elif not test_passed:
                comparison = state.context.get("test_comparison", {})
                new_fails = comparison.get("new_failures", []) if isinstance(comparison, dict) else []
                final_decision = "reject"
                state.decision_trace.append(
                    f"Rejected: patch introduced {len(new_fails)} new test failure(s): {new_fails[:5]}"
                )
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
                    git_ops=run_git_ops,
                    repo_ref=repo_ref,
                    issue_number=str(issue.number),
                    scribe_payload=scribe_result.payload,
                )
                state.context["github_finalize"] = gh_summary
                state.decision_trace.append(gh_summary)

        if ad_hoc_spent:
            state.decision_trace.append(
                f"Ad-hoc PatchPlanner budget usage: {ad_hoc_spent}/{score.ad_hoc_budget}."
            )

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
        workspace_diff = self._collect_workspace_diff(workspace_path)
        logger.write_artifact("patch.diff", workspace_diff or latest_patch or "# No patch generated\n")
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
            # fallback to local workspace if clone fails
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
