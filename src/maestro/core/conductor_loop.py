from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from maestro.agents.analyst import IssueAnalystAgent
from maestro.agents.base import AgentResult
from maestro.agents.critic import PatchReviewerAgent
from maestro.agents.maestro_conductor import ConductorDecision, MaestroConductorAgent
from maestro.agents.patch_planner import PatchStrategistAgent
from maestro.agents.scout import CodeExplorerAgent
from maestro.agents.scribe import ReleaseScribeAgent
from maestro.agents.surgeon import PatchAuthorAgent
from maestro.agents.tester import TestVerifierAgent
from maestro.config.settings import AppConfig
from maestro.core.ad_hoc_factory import AdHocAgentSpec, AdHocFactory
from maestro.core.context_brief import build_maestro_situation_report, enrich_subagent_context
from maestro.core.logger import EventLogger
from maestro.core.message import new_correlation_id
from maestro.core.state import RunState
from maestro.policies.agentic_fatigue import AgenticFatigueTracker
from maestro.policies.patch_signals import is_material_unified_diff
from maestro.policies.patch_scope import validate_patch_scope
from maestro.policies.patch_strategy import classify_change_scale
from maestro.policies.safety import evaluate_safety_gate
from maestro.policies.test_feedback import (
    build_test_repair_feedback,
    compare_test_results,
    targets_already_passing,
    test_focus_files_for_context,
)
from maestro.config.model_routing import ModelRouter
from maestro.providers.llm.base import LLMProvider
from maestro.providers.test_runner import TestRunner


class ConductorLoop:
    def __init__(
        self,
        *,
        config: AppConfig,
        llm: LLMProvider,
        model_router: ModelRouter,
        logger: EventLogger,
        state: RunState,
        ad_hoc_factory: AdHocFactory,
        test_runner: TestRunner,
        issue_ref: str,
    ) -> None:
        self.config = config
        self.llm = llm
        self.model_router = model_router
        self.logger = logger
        self.state = state
        self.ad_hoc_factory = ad_hoc_factory
        self.test_runner = test_runner
        self.issue_ref = issue_ref
        self.workspace_path = Path(str(state.context["workspace_path"]))
        self.fatigue_tracker = AgenticFatigueTracker()
        self.seen_patch_fingerprints: set[str] = set()
        self.repeated_patch_attempts = 0
        self.any_material_patch = False
        self.final_decision = "reject"
        self.human_escalation_reason = "conductor_escalation"
        self.last_dispatched_agent: str | None = None
        self.same_agent_dispatch_streak = 0
        self.last_reviewed_patch_fingerprint: str = ""
        self.same_patch_reject_streak = 0

        self.maestro = MaestroConductorAgent(llm, model_router.model_for("Maestro"))
        self.agents = {
            "IssueAnalyst": IssueAnalystAgent(llm, model_router.model_for("IssueAnalyst")),
            "CodeExplorer": CodeExplorerAgent(llm, model_router.model_for("CodeExplorer")),
            "PatchStrategist": PatchStrategistAgent(
                llm, model_router.model_for("PatchStrategist")
            ),
            "PatchAuthor": PatchAuthorAgent(llm, model_router.model_for("PatchAuthor")),
            "PatchReviewer": PatchReviewerAgent(llm, model_router.model_for("PatchReviewer")),
            "TestVerifier": TestVerifierAgent(
                llm, model_router.model_for("TestVerifier"), test_runner=test_runner
            ),
            "ReleaseScribe": ReleaseScribeAgent(llm, model_router.model_for("ReleaseScribe")),
        }

    def run(self) -> str:
        ctx = self.state.context
        ctx["mock_llm"] = self.config.runtime.mock_llm
        ctx["max_retries"] = self.config.runtime.max_retries
        ctx["ad_hoc_budget"] = self.state.score.ad_hoc_budget
        ctx["test_baseline_before_patch"] = self.config.runtime.test_baseline_before_patch
        ctx["test_repair_max_retries"] = self.config.runtime.test_repair_max_retries
        ctx["strict_scope_mode"] = self.config.runtime.strict_scope_mode
        ctx["require_target_tests"] = self.config.runtime.require_target_tests
        ctx["patch_retry_count"] = 0
        ctx["patch_strategist_spent"] = 0
        ctx["patch_approved"] = False
        ctx["patch_author_turns_since_reviewer"] = 0
        ctx["same_patch_reject_streak"] = 0
        ctx.pop("last_patch_review", None)
        ctx.pop("pending_patch_diff", None)

        max_steps = self.config.runtime.maestro_max_conductor_steps
        for step in range(max_steps):
            ctx["conductor_step"] = step + 1
            report = build_maestro_situation_report(ctx)
            decision = self.maestro.decide(ctx, situation_report=report)
            decision = self._apply_dispatch_guardrails(decision)
            self._trace(f"Maestro step {step + 1}: {decision.action} agent={decision.agent} — {decision.rationale}")
            self._dispatch(
                "Maestro",
                "Maestro",
                "decision",
                {
                  "action": decision.action,
                  "agent": decision.agent,
                  "task": decision.task,
                  "rationale": decision.rationale,
                },
                confidence=decision.confidence,
            )

            if decision.action == "human_escalation":
                self.human_escalation_reason = decision.rationale or "conductor_human_escalation"
                self._escalate(self.human_escalation_reason)
                self.final_decision = "human_escalation"
                return self.final_decision

            if decision.action == "finish_success":
                if self._can_finish_success():
                  self.final_decision = "commit_ready"
                  return self.final_decision
                if self._should_dispatch_scribe_before_finish():
                    self._trace(
                        "finish_success ready except ReleaseScribe; dispatching scribe before retry."
                    )
                    terminal = self._dispatch_agent("ReleaseScribe", "draft_commit_and_pr")
                    if terminal:
                        return terminal
                    continue
                self._trace("Maestro finish_success blocked by policy gates; continuing.")
                continue

            if decision.action == "finish_already_resolved":
                if not isinstance(self.state.context.get("scribe"), dict):
                    self._trace(
                        "finish_already_resolved arrived before ReleaseScribe ran; "
                        "forcing a scribe pass so the feedback artifact is written."
                    )
                    self._dispatch_agent(
                        "ReleaseScribe",
                        "draft_already_resolved_feedback",
                    )
                self.final_decision = "already_resolved"
                self._trace(
                    "Maestro finish_already_resolved: baseline shows the issue's target "
                    "tests already pass; emitting feedback artifact instead of a patch."
                )
                return self.final_decision

            if decision.action == "finish_reject":
                self.final_decision = "reject"
                return self.final_decision

            if decision.action == "spawn_patch_strategist":
                self._run_patch_strategist()
                continue

            if decision.action == "dispatch" and decision.agent:
                terminal = self._dispatch_agent(decision.agent, decision.task)
                if terminal:
                  return terminal
                continue

            self._trace(f"Unknown conductor action '{decision.action}'; stopping.")
            self.final_decision = "reject"
            return self.final_decision

        self.human_escalation_reason = "conductor_step_budget_exhausted"
        self._escalate(self.human_escalation_reason)
        self.final_decision = "human_escalation"
        return self.final_decision

    def _dispatch_agent(self, agent_name: str, task: str) -> str | None:
        agent = self.agents.get(agent_name)
        if agent is None:
            self._trace(f"Unknown agent '{agent_name}'.")
            return None
        if self.last_dispatched_agent == agent_name:
            self.same_agent_dispatch_streak += 1
        else:
            self.last_dispatched_agent = agent_name
            self.same_agent_dispatch_streak = 1
        ctx = enrich_subagent_context(self.state.context)
        self._dispatch("Maestro", agent_name, "task", {"task": task})

        if agent_name == "TestVerifier":
            return self._run_test_verifier(task)
        if agent_name == "PatchStrategist":
            self._run_patch_strategist()
            return None
        if agent_name == "PatchAuthor":
            return self._run_patch_author(task)
        if agent_name == "PatchReviewer":
            return self._run_patch_reviewer(task)

        if agent_name == "ReleaseScribe":
            scribe_ctx = dict(ctx)
            scribe_ctx["issue_ref"] = self.issue_ref
            scribe_ctx["scribe_task"] = task
            scribe_ctx["task_id"] = self.state.task_id
            result = agent.run(scribe_ctx)
            self.state.context["scribe"] = result.payload
            self._dispatch(agent_name, "Maestro", "result", result.payload, result.confidence)
            self.state.decision_trace.append(f"{agent_name}: {result.summary}")
        else:
            result = agent.run(ctx)
            self._merge_agent_result(agent_name, result)
        return None

    def _merge_agent_result(self, agent_name: str, result: AgentResult) -> None:
        self._dispatch(agent_name, "Maestro", "result", result.payload, result.confidence)
        if agent_name == "IssueAnalyst":
            self.state.context["analysis"] = result.payload
        elif agent_name == "CodeExplorer":
            self.state.context["scout"] = result.payload
        self.state.decision_trace.append(f"{agent_name}: {result.summary}")

    def _run_patch_strategist(self) -> None:
        spent = int(self.state.context.get("patch_strategist_spent", 0))
        budget = int(self.state.context.get("ad_hoc_budget", 0))
        if spent >= budget:
            self._trace("PatchStrategist budget exhausted.")
            return
        spec = AdHocAgentSpec(
            agent_name="PatchStrategist",
            creation_reason="Maestro spawned strategist for complex patch planning",
            role_spec="Produce JSON snippet edits constrained to explorer-ranked files.",
            tool_scope="read-only",
            ttl="single-invocation",
        )
        self.ad_hoc_factory.create(spec)
        ctx = enrich_subagent_context(self.state.context)
        result = self.agents["PatchStrategist"].run(ctx)
        plan = result.payload.get("patch_plan")
        if isinstance(plan, dict):
            self.state.context["patch_plan"] = plan
        self.ad_hoc_factory.close(spec, close_reason="plan_ready_for_patch_author")
        self.state.context["patch_strategist_spent"] = spent + 1
        self._dispatch("PatchStrategist", "Maestro", "result", result.payload, result.confidence)
        self.state.decision_trace.append(result.summary)

    def _run_patch_author(self, task: str) -> str | None:
        ctx = enrich_subagent_context(self.state.context)
        ctx["retry_count"] = int(self.state.context.get("patch_retry_count", 0))
        if task == "test_repair_patch":
            repair = int(self.state.context.get("test_repair_attempt", 0)) + 1
            self.state.context["test_repair_attempt"] = repair
            self._trace(f"Test repair pass {repair}/{self.state.context.get('test_repair_max_retries')}")

        self._ensure_patch_strategy_fields(ctx)
        self._dispatch("Maestro", "PatchAuthor", "task", {"task": task, "retry": ctx["retry_count"]})
        result = self.agents["PatchAuthor"].run(ctx)
        self.state.context["patch_author_turns_since_reviewer"] = int(
            self.state.context.get("patch_author_turns_since_reviewer", 0)
        ) + 1
        self.state.context.pop("patch_plan", None)
        self._dispatch("PatchAuthor", "Maestro", "result", result.payload, result.confidence)

        patch = str(result.payload.get("patch_diff", ""))
        material = is_material_unified_diff(patch)
        if material:
            scope_result = validate_patch_scope(
                patch,
                workspace=self.workspace_path,
                scout_payload=self.state.context.get("scout")
                if isinstance(self.state.context.get("scout"), dict)
                else None,
                baseline_payload=self.state.context.get("test_baseline")
                if isinstance(self.state.context.get("test_baseline"), dict)
                else None,
            )
            self.state.context["patch_scope"] = scope_result
            if self.config.runtime.strict_scope_mode and not scope_result.get("passed"):
                self._trace(
                    "PatchAuthor patch rejected by scope validator: "
                    f"{scope_result.get('violations', [])}"
                )
                self._dispatch("PatchScope", "Maestro", "decision", scope_result, 0.82)
                self._revert_rejected_patch(patch)
                self.state.context["patch_approved"] = False
                self.state.context["last_rejected_patch_diff"] = patch
                self.state.context["critic_feedback"] = [
                    "Patch edits symbols outside the selected issue target tests: "
                    + ", ".join(str(x) for x in scope_result.get("violations", []))
                ]
                self.state.context["patch_retry_count"] = int(
                    self.state.context.get("patch_retry_count", 0)
                ) + 1
                self.state.context.pop("pending_patch_diff", None)
                self.state.context.pop("patch_diff", None)
                self.state.context.pop("test_guided_patch", None)
                if self.state.context["patch_retry_count"] > int(
                    self.state.context.get("max_retries", 3)
                ):
                    self.human_escalation_reason = "scope_validator_retry_exhausted"
                    self._escalate(self.human_escalation_reason)
                    self.final_decision = "human_escalation"
                    return self.final_decision
                return None
            self.any_material_patch = True
            self.state.context["pending_patch_diff"] = patch
            if str(result.payload.get("strategy_used") or "") == "test_guided_repair":
                self.state.context["test_guided_patch"] = True
            else:
                self.state.context.pop("test_guided_patch", None)
            self.state.context.pop("last_patch_review", None)
        self._track_patch_fingerprint(result.payload)

        if not material:
            self._trace("PatchAuthor produced no material diff.")
            if self.repeated_patch_attempts >= 2:
                self.human_escalation_reason = "patch_author_repeated_non_material"
                self._escalate(self.human_escalation_reason)
                self.final_decision = "human_escalation"
                return self.final_decision
            self.state.context["patch_retry_count"] = int(self.state.context.get("patch_retry_count", 0)) + 1
        return None

    def _auto_approve_pending_patch(self, patch: str, *, reason: str) -> None:
        self.state.context["patch_approved"] = True
        self.state.context["patch_diff"] = patch
        self.state.context["critic_feedback"] = []
        self.state.context.pop("pending_patch_diff", None)
        self.state.decision_trace.append(f"PatchReviewer: approve ({reason})")

    def _run_patch_reviewer(self, task: str) -> str | None:
        patch = str(self.state.context.get("pending_patch_diff", ""))
        if not is_material_unified_diff(patch):
            self._trace("PatchReviewer skipped: no pending material patch.")
            return None
        if self.config.runtime.skip_patch_reviewer:
            self._auto_approve_pending_patch(patch, reason="ablation skip_patch_reviewer")
            return None
        self.state.context["patch_author_turns_since_reviewer"] = 0
        retry = int(self.state.context.get("patch_retry_count", 0))
        ctx = self._critic_context(enrich_subagent_context(self.state.context), patch, retry)
        self._dispatch("Maestro", "PatchReviewer", "task", {"task": task, "retry": retry})
        result = self.agents["PatchReviewer"].run(ctx)
        self._dispatch("PatchReviewer", "Maestro", "feedback", result.payload, result.confidence)

        decision = str(result.payload.get("decision", "reject"))
        patch_fp = hashlib.sha1(patch.encode("utf-8")).hexdigest()
        if decision == "reject":
            if patch_fp == self.last_reviewed_patch_fingerprint:
                self.same_patch_reject_streak += 1
            else:
                self.same_patch_reject_streak = 1
        else:
            self.same_patch_reject_streak = 0
        self.last_reviewed_patch_fingerprint = patch_fp
        self.state.context["same_patch_reject_streak"] = self.same_patch_reject_streak
        fatigue = self._fatigue_after_review(result, retry)
        review_record = {
            "decision": decision,
            "confidence": result.payload.get("confidence"),
            "feedback": result.payload.get("feedback", []),
        }
        self.state.context["last_patch_review"] = review_record
        self.state.decision_trace.append(f"PatchReviewer: {decision}")

        if fatigue:
            self.human_escalation_reason = fatigue
            self.state.context["agentic_fatigue"] = self.fatigue_tracker.summary()
            self._escalate(fatigue)
            self.final_decision = "human_escalation"
            return self.final_decision

        if decision == "approve":
            self.state.context["patch_approved"] = True
            self.state.context["patch_diff"] = patch
            self.state.context["critic_feedback"] = list(result.payload.get("feedback", []))
            self.state.context.pop("pending_patch_diff", None)
            return None

        # Reviewer rejected this candidate; clear pending patch so Maestro must ask PatchAuthor
        # for a fresh revision instead of re-reviewing the same diff in a loop.
        self._revert_rejected_patch(patch)
        self.state.context["patch_approved"] = False
        self.state.context["last_rejected_patch_diff"] = patch
        self.state.context["critic_feedback"] = list(result.payload.get("feedback", []))
        self.state.context.pop("pending_patch_diff", None)
        self.state.context["patch_retry_count"] = retry + 1
        if self.state.context["patch_retry_count"] > int(self.state.context.get("max_retries", 3)):
            self.human_escalation_reason = "patch_review_retry_exhausted"
            self._escalate(self.human_escalation_reason)
            self.final_decision = "human_escalation"
            return self.final_decision
        return None

    def _run_test_verifier(self, task: str) -> str | None:
        ctx = enrich_subagent_context(self.state.context)
        if task == "baseline":
            self._dispatch("Maestro", "TestVerifier", "task", {"task": "baseline"})
            result = self.agents["TestVerifier"].run(ctx)
            self.state.context["test_baseline"] = result.payload
            self._dispatch("TestVerifier", "Maestro", "result", result.payload, result.confidence)
            if not result.payload.get("passed"):
                self.state.context["baseline_test_feedback"] = (
                  "Pre-patch tests failed.\n\n" + str(result.payload.get("stderr") or "")[:4500]
                )
            else:
                self.state.context.pop("baseline_test_feedback", None)
            self.state.decision_trace.append(
                f"TestVerifier baseline: passed={result.payload.get('passed')}"
            )
            target_labels = self._scout_target_labels()
            if targets_already_passing(
                target_failures=target_labels,
                baseline=result.payload if isinstance(result.payload, dict) else None,
            ):
                self.state.context["target_already_resolved"] = True
                self.state.context["target_already_resolved_targets"] = list(target_labels or [])
                self._trace(
                    "Baseline already proves Scout's target tests pass: "
                    f"{target_labels}. Switching to already_resolved feedback path."
                )
                self._dispatch(
                    "Maestro",
                    "TestVerifier",
                    "feedback",
                    {
                        "target_already_resolved": True,
                        "targets": list(target_labels or []),
                    },
                    confidence=0.9,
                )
            return None

        self._dispatch("Maestro", "TestVerifier", "task", {"task": "verify"})
        self.state.context["patch_author_turns_since_reviewer"] = 0
        result = self.agents["TestVerifier"].run(ctx)
        self.state.context["test_result"] = result.payload
        self._dispatch("TestVerifier", "Maestro", "result", result.payload, result.confidence)
        comparison = compare_test_results(
            baseline=self.state.context.get("test_baseline")
            if isinstance(self.state.context.get("test_baseline"), dict)
            else None,
            post_patch=result.payload,
            require_fix_on_red_baseline=self.config.runtime.require_fix_on_red_baseline,
            target_failures=self._scout_target_labels(),
        )
        self.state.context["test_comparison"] = comparison
        self._dispatch("Maestro", "TestVerifier", "feedback", {"test_comparison": comparison}, 0.83)
        self.state.decision_trace.append(f"TestVerifier: {comparison.get('summary')}")
        if not comparison.get("scope_clean", True):
            self.state.decision_trace.append(
                "Scope warning: patch fixed out-of-scope failures "
                f"{comparison.get('unsolicited_fixes', [])}"
            )

        if comparison.get("issue_resolved"):
            pending_patch = str(self.state.context.get("pending_patch_diff", ""))
            if is_material_unified_diff(pending_patch):
                self.state.context["patch_diff"] = pending_patch
                self.state.context.pop("pending_patch_diff", None)
            self.state.context["patch_approved"] = True
            self.state.context.pop("test_guided_patch", None)
            return None

        if not comparison.get("issue_resolved"):
            failed_patch = str(self.state.context.get("patch_diff", ""))
            if not is_material_unified_diff(failed_patch):
                failed_patch = str(self.state.context.get("pending_patch_diff", ""))
            self._revert_rejected_patch(failed_patch)
            stderr = str(result.payload.get("stderr") or "")
            self.state.context["test_failure_feedback"] = build_test_repair_feedback(
                self.state.context.get("test_baseline")
                if isinstance(self.state.context.get("test_baseline"), dict)
                else None,
                result.payload,
                workspace=self.workspace_path,
            )
            self.state.context["test_focus_files"] = test_focus_files_for_context(
                stderr, self.workspace_path
            )
            scout = self.state.context.get("scout")
            if isinstance(scout, dict):
                candidates = list(scout.get("candidate_files", []))
                for f in self.state.context.get("test_focus_files", []):
                  if f not in candidates:
                      candidates.append(f)
                self.state.context["scout"] = {**scout, "candidate_files": candidates}
            self.state.context["patch_approved"] = False
            self.state.context.pop("last_patch_review", None)
            self.state.context.pop("pending_patch_diff", None)
            self.state.context.pop("patch_diff", None)
            self.state.context.pop("test_guided_patch", None)
        return None

    _PHASE_PROGRESSION: dict[str, str] = {
        "IssueAnalyst": "CodeExplorer",
        "CodeExplorer": "PatchAuthor",
        "TestVerifier": "PatchAuthor",
    }
    _MAX_SAME_AGENT_STREAK = 2

    def _apply_dispatch_guardrails(self, decision: ConductorDecision) -> ConductorDecision:
        if decision.action != "dispatch" or not decision.agent:
            return decision

        agent = decision.agent
        task = self._normalize_task(agent, decision.task)
        decision.task = task
        ctx = self.state.context

        if self.same_agent_dispatch_streak >= self._MAX_SAME_AGENT_STREAK and agent == self.last_dispatched_agent:
            next_agent = self._PHASE_PROGRESSION.get(agent)
            if next_agent:
                self._trace(f"Guardrail: {agent} dispatched {self.same_agent_dispatch_streak}x; advancing to {next_agent}.")
                return ConductorDecision(
                    action="dispatch",
                    agent=next_agent,
                    task=self._normalize_task(next_agent, ""),
                    rationale=f"Guardrail: {agent} repeated {self.same_agent_dispatch_streak}x without phase progress; forcing {next_agent}.",
                    confidence=max(decision.confidence, 0.82),
                )

        has_analysis = isinstance(ctx.get("analysis"), dict)
        has_scout = isinstance(ctx.get("scout"), dict)
        has_baseline = isinstance(ctx.get("test_baseline"), dict)
        has_patch_plan = isinstance(ctx.get("patch_plan"), dict)
        pending_patch = is_material_unified_diff(str(ctx.get("pending_patch_diff", "")))
        patch_approved = bool(ctx.get("patch_approved"))
        comparison = ctx.get("test_comparison")
        scout = ctx.get("scout")

        if bool(ctx.get("target_already_resolved")):
            if not isinstance(ctx.get("scribe"), dict) and agent != "ReleaseScribe":
                return ConductorDecision(
                    action="dispatch",
                    agent="ReleaseScribe",
                    task="draft_already_resolved_feedback",
                    rationale=(
                        "Guardrail: baseline already proves Scout's target tests pass; "
                        "skip patch authoring and produce an already-resolved feedback report."
                    ),
                    confidence=max(decision.confidence, 0.92),
                )
            if isinstance(ctx.get("scribe"), dict):
                return ConductorDecision(
                    action="finish_already_resolved",
                    rationale=(
                        "Guardrail: target tests already green in baseline and feedback "
                        "artifact drafted; closing run without a patch."
                    ),
                    confidence=max(decision.confidence, 0.94),
                )

        if isinstance(scout, dict):
            raw_targets = scout.get("target_tests")
            target_tests = raw_targets if isinstance(raw_targets, list) else []
            if bool(scout.get("target_selection_blocking")) and not target_tests:
                return ConductorDecision(
                    action="human_escalation",
                    rationale=(
                        "Scout could not confidently map the issue to any existing test. "
                        "Stopping instead of falling back to unrelated failing tests."
                    ),
                    confidence=max(decision.confidence, 0.9),
                )
            if (
                bool(ctx.get("require_target_tests"))
                and has_scout
                and not target_tests
                and agent != "CodeExplorer"
            ):
                return ConductorDecision(
                    action="human_escalation",
                    rationale=(
                        "Target tests are required but Scout returned none; cannot safely "
                        "continue with issue-scoped automation."
                    ),
                    confidence=max(decision.confidence, 0.88),
                )

        if (
            patch_approved
            and isinstance(comparison, dict)
            and bool(comparison.get("issue_resolved"))
        ):
            if not isinstance(ctx.get("scribe"), dict) and agent != "ReleaseScribe":
                return ConductorDecision(
                    action="dispatch",
                    agent="ReleaseScribe",
                    task="draft_commit_and_pr",
                    rationale="Guardrail: verified patch resolved the issue; drafting release notes before finish.",
                    confidence=max(decision.confidence, 0.9),
                )
            return ConductorDecision(
                action="finish_success",
                rationale="Guardrail: verified patch resolved the issue; finishing successfully.",
                confidence=max(decision.confidence, 0.9),
            )

        if pending_patch and bool(ctx.get("test_guided_patch")) and agent != "TestVerifier":
            return ConductorDecision(
                action="dispatch",
                agent="TestVerifier",
                task="verify",
                rationale="Guardrail: test-guided patch should be validated by tests before model review.",
                confidence=max(decision.confidence, 0.88),
            )

        if pending_patch and agent != "PatchReviewer":
            if self.config.runtime.skip_patch_reviewer:
                patch = str(ctx.get("pending_patch_diff", ""))
                if is_material_unified_diff(patch):
                    self._auto_approve_pending_patch(
                        patch, reason="ablation skip_patch_reviewer guardrail"
                    )
            else:
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchReviewer",
                    task="review_patch",
                    rationale="Guardrail: material patch exists; review before any other phase.",
                    confidence=max(decision.confidence, 0.84),
                )

        if patch_approved and agent != "TestVerifier":
            return ConductorDecision(
                action="dispatch",
                agent="TestVerifier",
                task="verify",
                rationale="Guardrail: approved patch must be verified before any other phase.",
                confidence=max(decision.confidence, 0.84),
            )

        if self.config.runtime.skip_triage_agents and agent in ("IssueAnalyst", "CodeExplorer"):
            if not has_baseline:
                return ConductorDecision(
                    action="dispatch",
                    agent="TestVerifier",
                    task="baseline",
                    rationale="Ablation skip_triage_agents: run baseline before patching.",
                    confidence=max(decision.confidence, 0.85),
                )
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="author_patch",
                rationale="Ablation skip_triage_agents: triage skipped; patching from baseline.",
                confidence=max(decision.confidence, 0.82),
            )

        if agent == "IssueAnalyst" and has_analysis and (has_scout or has_baseline):
            self._trace("Guardrail: blocking IssueAnalyst regression; analysis and scout already done.")
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="author_patch",
                rationale="Guardrail: analysis is complete and repair context exists; IssueAnalyst is no longer needed.",
                confidence=max(decision.confidence, 0.82),
            )

        if agent == "CodeExplorer" and has_scout and has_baseline:
            self._trace("Guardrail: blocking CodeExplorer regression; scout and baseline already done.")
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="author_patch",
                rationale="Guardrail: code exploration and baseline complete; advancing to PatchAuthor.",
                confidence=max(decision.confidence, 0.82),
            )

        patch_author_turns = int(ctx.get("patch_author_turns_since_reviewer", 0))
        same_patch_rejects = int(ctx.get("same_patch_reject_streak", 0))

        if agent == "PatchStrategist":
            baseline_feedback = str(ctx.get("baseline_test_feedback") or "")
            if all(
                marker in baseline_feedback
                for marker in (
                    "test_cancel_frees_room",
                    "test_invoice_extra_charges_isolation",
                    "test_negative_nights_validation",
                )
            ):
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchAuthor",
                    task="author_patch",
                    rationale="Guardrail: baseline tests contain deterministic repair signals; skipping strategist.",
                    confidence=max(decision.confidence, 0.88),
                )
            strategist_spent = int(ctx.get("patch_strategist_spent", 0))
            strategist_budget = int(ctx.get("ad_hoc_budget", 0))
            if has_patch_plan or strategist_spent >= strategist_budget:
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchAuthor",
                    task="author_patch",
                    rationale="Guardrail: patch strategy is ready or budget is spent; moving to PatchAuthor.",
                    confidence=max(decision.confidence, 0.82),
                )

        if agent == "PatchAuthor":
            if pending_patch:
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchReviewer",
                    task="review_patch",
                    rationale="Guardrail: material patch exists; review before another author pass.",
                    confidence=max(decision.confidence, 0.82),
                )
            if patch_approved:
                return ConductorDecision(
                    action="dispatch",
                    agent="TestVerifier",
                    task="verify",
                    rationale="Guardrail: approved patch must be verified before further authoring.",
                    confidence=max(decision.confidence, 0.82),
                )
            if patch_author_turns >= 2:
                self._trace("Guardrail: PatchAuthor repeated without material patch; allowing revision instead of reviewer skip loop.")
                decision.task = "revise_patch"

        if agent == "PatchReviewer" and not pending_patch:
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="revise_patch",
                rationale="Guardrail: no pending patch to review; force author revision.",
                confidence=max(decision.confidence, 0.78),
            )
        if agent == "PatchReviewer" and pending_patch and same_patch_rejects >= 2:
            strategist_spent = int(ctx.get("patch_strategist_spent", 0))
            strategist_budget = int(ctx.get("ad_hoc_budget", 0))
            if strategist_spent < strategist_budget:
                return ConductorDecision(
                    action="spawn_patch_strategist",
                    rationale="Guardrail: same patch repeatedly rejected; request strategist plan.",
                    confidence=max(decision.confidence, 0.84),
                )
            return ConductorDecision(
                action="dispatch",
                agent="PatchAuthor",
                task="revise_patch",
                rationale="Guardrail: same patch repeatedly rejected; force author revision.",
                confidence=max(decision.confidence, 0.84),
            )

        if agent == "TestVerifier":
            if task not in {"baseline", "verify"}:
                decision.task = "verify"
            if task == "baseline" and isinstance(ctx.get("test_baseline"), dict):
                if not pending_patch:
                    return ConductorDecision(
                        action="dispatch",
                        agent="PatchAuthor",
                        task="author_patch",
                        rationale="Guardrail: baseline already recorded; no patch yet, moving to PatchAuthor.",
                        confidence=max(decision.confidence, 0.82),
                    )
                return ConductorDecision(
                    action="dispatch",
                    agent="PatchReviewer",
                    task="review_patch",
                    rationale="Guardrail: baseline already recorded and patch exists; moving to review.",
                    confidence=max(decision.confidence, 0.82),
                )
        return decision

    _SCRIBE_TASKS = {"draft_commit_and_pr", "draft_already_resolved_feedback"}

    def _normalize_task(self, agent: str, task: str) -> str:
        task_raw = str(task or "").strip()
        if task_raw and task_raw.lower() != "none":
            if agent == "ReleaseScribe" and task_raw not in self._SCRIBE_TASKS:
                return "draft_commit_and_pr"
            return task_raw
        defaults = {
            "IssueAnalyst": "decompose_issue",
            "CodeExplorer": "discover_code_context",
            "PatchAuthor": "author_patch",
            "PatchReviewer": "review_patch",
            "TestVerifier": "verify",
            "PatchStrategist": "plan_patch_snippets",
            "ReleaseScribe": "draft_commit_and_pr",
        }
        return defaults.get(agent, "execute")

    def _scout_target_labels(self) -> list[str] | None:
        """Pull Scout's issue-scoped test identifiers for the test_feedback comparator.

        Prefer ``target_test_dotted`` (canonical unittest ids). Scout's LLM
        sometimes emits human hint strings in ``target_test_labels`` (e.g.
        "Book a room, cancel it…") which do not appear in unittest stderr and
        would falsely trigger ``targets_already_passing``.

        Returns ``None`` when Scout has not run or produced no targets — that
        signals ``compare_test_results`` to fall back to legacy semantics.
        """
        scout = self.state.context.get("scout")
        if not isinstance(scout, dict):
            return None
        dotted = scout.get("target_test_dotted")
        if isinstance(dotted, list) and dotted:
            out = [str(x) for x in dotted if str(x).strip()]
            if out:
                return out
        labels = scout.get("target_test_labels")
        if isinstance(labels, list) and labels:
            out = [str(x) for x in labels if str(x).strip()]
            return out or None
        return None

    def _should_dispatch_scribe_before_finish(self) -> bool:
        """True when the run is ready to finish but ReleaseScribe has not run yet."""
        ctx = self.state.context
        if isinstance(ctx.get("scribe"), dict):
            return False
        if not self.any_material_patch:
            return False
        comparison = ctx.get("test_comparison")
        if not isinstance(comparison, dict) or not comparison.get("issue_resolved"):
            return False
        if self.config.runtime.strict_scope_mode and not comparison.get("scope_clean", True):
            return False
        if self.config.runtime.require_target_tests:
            scout = ctx.get("scout")
            scout_targets: list[Any] = []
            if isinstance(scout, dict):
                raw_targets = scout.get("target_tests")
                if isinstance(raw_targets, list):
                    scout_targets = list(raw_targets)
            if not scout_targets:
                return False
        safety = evaluate_safety_gate(ctx)
        return bool(safety.get("passed"))

    def _can_finish_success(self) -> bool:
        ctx = self.state.context
        if not self.any_material_patch:
            self._trace("Blocked finish_success: no material patch.")
            return False
        comparison = ctx.get("test_comparison")
        if not isinstance(comparison, dict) or not comparison.get("issue_resolved"):
            self._trace("Blocked finish_success: tests did not resolve issue.")
            return False
        if self.config.runtime.strict_scope_mode and not comparison.get("scope_clean", True):
            self._trace(
                "Blocked finish_success (strict_scope_mode): patch fixed out-of-scope "
                f"failures {comparison.get('unsolicited_fixes', [])}; "
                "expected to leave them for separate issues."
            )
            self.human_escalation_reason = "scope_creep_detected"
            self.final_decision = "human_escalation"
            return False
        if self.config.runtime.require_target_tests:
            scout = ctx.get("scout")
            scout_targets: list[Any] = []
            if isinstance(scout, dict):
                raw_targets = scout.get("target_tests")
                if isinstance(raw_targets, list):
                    scout_targets = list(raw_targets)
            if not scout_targets:
                self._trace(
                    "Blocked finish_success (require_target_tests): Scout returned no "
                    "target_tests; cannot confirm patch is issue-scoped."
                )
                self.human_escalation_reason = "missing_target_tests"
                self.final_decision = "human_escalation"
                return False
        safety = evaluate_safety_gate(ctx)
        self._dispatch("Maestro", "SafetyGate", "decision", safety, 0.79)
        if not safety.get("passed"):
            self._trace(f"Blocked finish_success: safety ({safety.get('reason')}).")
            self.final_decision = "reject"
            return False
        if not isinstance(ctx.get("scribe"), dict):
            self._trace("Blocked finish_success: ReleaseScribe not run yet.")
            return False
        return True

    def _ensure_patch_strategy_fields(self, ctx: dict[str, Any]) -> None:
        if "change_scale" not in ctx:
            ctx["change_scale"] = classify_change_scale(self.state.context)
        ctx["strategy_max_diff_lines"] = self.config.runtime.patch_strategy_max_diff_lines
        ctx["strategy_max_diff_bytes"] = self.config.runtime.patch_strategy_max_diff_bytes
        ctx["rewrite_enabled"] = self.config.runtime.patch_strategy_rewrite_enabled
        ctx["hunk_enabled"] = self.config.runtime.patch_strategy_hunk_enabled
        ctx["snippet_enabled"] = self.config.runtime.patch_strategy_snippet_enabled

    def _track_patch_fingerprint(self, payload: dict[str, object]) -> None:
        status = str(payload.get("surgeon_status") or "")
        attempts = str(payload.get("strategy_attempts") or "")
        fp = hashlib.sha1(f"{status}|{attempts}".encode()).hexdigest()
        if fp in self.seen_patch_fingerprints:
            self.repeated_patch_attempts += 1
        else:
            self.seen_patch_fingerprints.add(fp)
            self.repeated_patch_attempts = 0

    def _revert_rejected_patch(self, patch: str) -> None:
        if not is_material_unified_diff(patch):
            return
        try:
            proc = subprocess.run(
                ["git", "apply", "-R", "--whitespace=nowarn"],
                input=patch,
                text=True,
                cwd=self.workspace_path,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._trace(f"Could not revert rejected patch: {exc}")
            return
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            self._trace(f"Could not revert rejected patch: {detail}")
            return
        self._trace("Reverted rejected patch from workspace.")

    def _fatigue_after_review(self, result: AgentResult, retry: int) -> str | None:
        decision = str(result.payload.get("decision", "reject"))
        conf_raw = result.payload.get("confidence")
        confidence = float(conf_raw) if isinstance(conf_raw, (int, float)) else 0.0
        from_llm = bool(result.payload.get("confidence_from_llm", False))
        self.fatigue_tracker.record(
            decision=decision,
            confidence=confidence,
            retry_index=retry,
            confidence_from_llm=from_llm,
        )
        if decision != "approve" or not self.config.runtime.agentic_fatigue_escalation_enabled:
            return None
        escalate, reason = self.fatigue_tracker.evaluate_compromise(
            min_rejects=self.config.runtime.agentic_fatigue_min_rejects,
            compromise_max_confidence=self.config.runtime.agentic_fatigue_compromise_max_confidence,
            confidence_drop_min=self.config.runtime.agentic_fatigue_confidence_drop_min,
            require_both_signals=self.config.runtime.agentic_fatigue_require_both_signals,
            require_explicit_confidence=self.config.runtime.agentic_fatigue_require_explicit_confidence,
        )
        return reason if escalate else None

    def _critic_context(
        self, base: dict[str, object], patch_diff: str, retry_count: int
  ) -> dict[str, object]:
        ctx = dict(base)
        ctx["patch_diff"] = patch_diff
        ctx["retry_count"] = retry_count
        ctx["max_retries"] = self.config.runtime.max_retries
        ctx["critic_final_retry_min_confidence"] = (
            self.config.runtime.critic_final_retry_min_confidence
        )
        return ctx

    def _escalate(self, reason: str) -> None:
        payload: dict[str, object] = {"reason": reason}
        if self.state.context.get("agentic_fatigue"):
            payload["agentic_fatigue"] = self.state.context["agentic_fatigue"]
        self._dispatch(
            "Maestro",
            "Human",
            "escalation",
            payload,
            confidence=0.84,
            blocking_reason="conductor_escalation",
        )
        self.state.decision_trace.append(f"Escalated: {reason}")

    def _trace(self, line: str) -> None:
        self.state.decision_trace.append(line)

    def _dispatch(
        self,
        sender: str,
        receiver: str,
        event_type: str,
        content: dict[str, object],
        confidence: float | None = None,
        blocking_reason: str | None = None,
        ) -> None:
        from maestro.core.message import OrchestrationEvent

        self.logger.log_event(
            OrchestrationEvent(
                task_id=self.state.task_id,
                correlation_id=new_correlation_id(),
                sender=sender,
                receiver=receiver,
                type=event_type,  # type: ignore[arg-type]
                content=content,
                confidence=confidence,
                blocking_reason=blocking_reason,
            )
        )
