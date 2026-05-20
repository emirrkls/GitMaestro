from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback for minimal environments
    yaml = None


@dataclass(slots=True)
class RuntimeConfig:
    mock_llm: bool
    allow_commit: bool
    allow_push: bool
    max_retries: int
    ad_hoc_budget: int
    test_timeout_seconds: int
    test_command_allowlist: list[str]
    github_enabled: bool
    allow_pr_draft: bool
    branch_prefix: str
    #: "cloud" (Gemini+OpenRouter), "ollama" (free local), or "hybrid" (prefix-routed local+nvidia).
    llm_backend: str
    #: OpenAI-compat base including /v1 e.g. http://127.0.0.1:11434/v1
    ollama_base_url: str
    #: Chat completion cap for Ollama (OpenAI field name: max_tokens)
    ollama_max_tokens: int
    #: Run the same test discovery once before any Surgeon edits (audit pre-existing reds).
    test_baseline_before_patch: bool
    #: After Critic-approved patch, how many extra Surgeon→Critic→Tester repair rounds on failure.
    test_repair_max_retries: int
    #: Red baseline: require at least one fixed failure (or full pass), not only no_regression.
    require_fix_on_red_baseline: bool
    #: Restrict patch scope to the failing tests Scout selected as target_tests for the issue.
    #: When true, fixing red tests that Scout marked out-of-scope blocks finish_success and
    #: forces ReleaseScribe to flag the scope creep in the PR body.
    strict_scope_mode: bool
    #: When true, IssueAnalyst/Scout MUST emit at least one target_test or Maestro escalates.
    #: When false, missing target_tests fall back to the legacy "all failing tests are targets"
    #: behavior (compatible with pre-scope-discipline runs).
    require_target_tests: bool
    #: When true, terminal states that produce ``issue_feedback.md`` (``already_resolved``,
    #: ``scope_violation_review``) also POST the feedback to the GitHub issue as a comment.
    #: Idempotent via a ``<!-- gitmaestro:run-id=... -->`` marker so retries do not spam.
    post_issue_feedback_comments: bool
    #: Maximum Maestro conductor steps per run (each step = one routing decision).
    maestro_max_conductor_steps: int
    #: Minimum Critic confidence to approve on the final Surgeon retry (anti agentic fatigue).
    critic_final_retry_min_confidence: float
    #: Escalate to human when Critic approves after repeated rejects with compromise signals.
    agentic_fatigue_escalation_enabled: bool
    #: Minimum consecutive Critic rejects immediately before an approve to consider fatigue.
    agentic_fatigue_min_rejects: int
    #: Approve confidence below this after a reject streak triggers escalation.
    agentic_fatigue_compromise_max_confidence: float
    #: Escalate when approve confidence drops this much below the max prior reject confidence.
    agentic_fatigue_confidence_drop_min: float
    #: Require both low approve confidence and a confidence drop (reduces false escalations).
    agentic_fatigue_require_both_signals: bool
    #: Ignore heuristic/default Critic confidence when evaluating fatigue.
    agentic_fatigue_require_explicit_confidence: bool
    #: Ollama chat: enable extended reasoning (`think: true`) for supported models; or "low"/"medium"/"high" for GPT-OSS.
    ollama_think: bool | str
    #: Full HTTP timeout for each Ollama /v1/chat/completions call (first load + think can be slow).
    ollama_timeout_seconds: int
    #: NVIDIA OpenAI-compatible base URL (without /chat/completions suffix).
    nvidia_base_url: str
    #: Full HTTP timeout for each NVIDIA chat completion call.
    nvidia_timeout_seconds: int
    #: Max output tokens for NVIDIA chat completion calls.
    nvidia_max_tokens: int
    #: Per-minute request cap applied client-side for NVIDIA calls (0 disables limiter).
    nvidia_rpm_limit: int
    #: Optional per-model RPM overrides for NVIDIA, e.g. {"meta/llama-3.3-70b-instruct": 10}.
    nvidia_rpm_overrides: dict[str, int]
    patch_strategy_snippet_enabled: bool
    patch_strategy_hunk_enabled: bool
    patch_strategy_rewrite_enabled: bool
    patch_strategy_max_diff_lines: int
    patch_strategy_max_diff_bytes: int
    #: Ablation: auto-approve material patches without PatchReviewer (Part 5 V1).
    skip_patch_reviewer: bool
    #: Ablation: skip IssueAnalyst and CodeExplorer; baseline then PatchAuthor (Part 5 V2).
    skip_triage_agents: bool


@dataclass(slots=True)
class ModelConfig:
    default: str
    critic: str
    ad_hoc_overrides: dict[str, str]


@dataclass(slots=True)
class AppConfig:
    models: ModelConfig
    runtime: RuntimeConfig


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        striped = line.strip()
        if not striped or striped.startswith("#") or "=" not in striped:
            continue
        key, value = striped.split("=", 1)
        os.environ[key.strip()] = value.strip()


def load_config(config_path: Path, env_path: Path | None = None) -> AppConfig:
    if env_path:
        load_env_file(env_path)

    raw_config = config_path.read_text(encoding="utf-8")
    if yaml is not None:
        payload: dict[str, Any] = yaml.safe_load(raw_config) or {}
    else:
        payload = _parse_minimal_yaml(raw_config)
    models = payload.get("models", {})
    runtime = payload.get("runtime", {})

    env_mock = os.getenv("MOCK_LLM")
    mock_llm = runtime.get("mock_llm", True)
    if env_mock is not None:
        mock_llm = env_mock.lower() == "true"

    return AppConfig(
        models=ModelConfig(
            default=models.get("default", "gemini-2.5-flash"),
            critic=models.get("critic", "llama-4-scout"),
            ad_hoc_overrides=models.get("ad_hoc_overrides", {}),
        ),
        runtime=RuntimeConfig(
            mock_llm=bool(mock_llm),
            allow_commit=bool(runtime.get("allow_commit", False)),
            allow_push=bool(runtime.get("allow_push", False)),
            max_retries=int(runtime.get("max_retries", 3)),
            ad_hoc_budget=int(runtime.get("ad_hoc_budget", 1)),
            test_timeout_seconds=int(runtime.get("test_timeout_seconds", 120)),
            test_command_allowlist=list(
                runtime.get(
                    "test_command_allowlist",
                    ["python -m unittest", "pytest", "python -m pytest"],
                )
            ),
            github_enabled=bool(runtime.get("github_enabled", True)),
            allow_pr_draft=bool(runtime.get("allow_pr_draft", False)),
            branch_prefix=str(runtime.get("branch_prefix", "maestro/issue")),
            llm_backend=str(runtime.get("llm_backend", "cloud")).strip().lower(),
            ollama_base_url=str(
                runtime.get("ollama_base_url", "http://127.0.0.1:11434/v1")
            ).strip(),
            ollama_max_tokens=int(runtime.get("ollama_max_tokens", 8192)),
            test_baseline_before_patch=bool(runtime.get("test_baseline_before_patch", True)),
            test_repair_max_retries=int(runtime.get("test_repair_max_retries", 2)),
            require_fix_on_red_baseline=bool(runtime.get("require_fix_on_red_baseline", True)),
            strict_scope_mode=bool(runtime.get("strict_scope_mode", True)),
            require_target_tests=bool(runtime.get("require_target_tests", False)),
            post_issue_feedback_comments=bool(
                runtime.get("post_issue_feedback_comments", False)
            ),
            maestro_max_conductor_steps=int(runtime.get("maestro_max_conductor_steps", 48)),
            critic_final_retry_min_confidence=float(
                runtime.get("critic_final_retry_min_confidence", 0.92)
            ),
            agentic_fatigue_escalation_enabled=bool(
                runtime.get("agentic_fatigue_escalation_enabled", True)
            ),
            agentic_fatigue_min_rejects=int(runtime.get("agentic_fatigue_min_rejects", 3)),
            agentic_fatigue_compromise_max_confidence=float(
                runtime.get("agentic_fatigue_compromise_max_confidence", 0.78)
            ),
            agentic_fatigue_confidence_drop_min=float(
                runtime.get("agentic_fatigue_confidence_drop_min", 0.18)
            ),
            agentic_fatigue_require_both_signals=bool(
                runtime.get("agentic_fatigue_require_both_signals", True)
            ),
            agentic_fatigue_require_explicit_confidence=bool(
                runtime.get("agentic_fatigue_require_explicit_confidence", True)
            ),
            ollama_think=_coerce_ollama_think(runtime.get("ollama_think", False)),
            ollama_timeout_seconds=max(60, int(runtime.get("ollama_timeout_seconds", 600))),
            nvidia_base_url=str(
                runtime.get("nvidia_base_url", "https://integrate.api.nvidia.com/v1")
            ).strip(),
            nvidia_timeout_seconds=max(10, int(runtime.get("nvidia_timeout_seconds", 90))),
            nvidia_max_tokens=max(256, int(runtime.get("nvidia_max_tokens", 4096))),
            nvidia_rpm_limit=max(0, int(runtime.get("nvidia_rpm_limit", 30))),
            nvidia_rpm_overrides=_coerce_int_dict(runtime.get("nvidia_rpm_overrides", {})),
            patch_strategy_snippet_enabled=bool(runtime.get("patch_strategy_snippet_enabled", True)),
            patch_strategy_hunk_enabled=bool(runtime.get("patch_strategy_hunk_enabled", True)),
            patch_strategy_rewrite_enabled=bool(runtime.get("patch_strategy_rewrite_enabled", False)),
            patch_strategy_max_diff_lines=max(20, int(runtime.get("patch_strategy_max_diff_lines", 600))),
            patch_strategy_max_diff_bytes=max(1000, int(runtime.get("patch_strategy_max_diff_bytes", 100_000))),
            skip_patch_reviewer=bool(runtime.get("skip_patch_reviewer", False)),
            skip_triage_agents=bool(runtime.get("skip_triage_agents", False)),
        ),
    )


def _coerce_ollama_think(raw: object) -> bool | str:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
        if s in ("low", "medium", "high"):
            return s
    return False


def _parse_minimal_yaml(raw: str) -> dict[str, Any]:
    # Minimal parser for this MVP config shape.
    result: dict[str, Any] = {"models": {}, "runtime": {}}
    section: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            section = stripped[:-1]
            if section not in result:
                result[section] = {}
            continue
        if ":" not in stripped or section is None:
            continue
        key, value = (part.strip() for part in stripped.split(":", 1))
        parsed: Any = value.strip('"').strip("'")
        if parsed.lower() in ("true", "false"):
            parsed = parsed.lower() == "true"
        elif parsed.isdigit():
            parsed = int(parsed)
        elif parsed.startswith("[") and parsed.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in parsed[1:-1].split(",") if x.strip()]
            parsed = items
        elif parsed == "{}":
            parsed = {}
        result[section][key] = parsed
    return result


def _coerce_int_dict(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        try:
            out[key] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return out
