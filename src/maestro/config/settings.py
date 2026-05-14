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
    #: "cloud" (Gemini+OpenRouter) or "ollama" (free local inference)
    llm_backend: str
    #: OpenAI-compat base including /v1 e.g. http://127.0.0.1:11434/v1
    ollama_base_url: str
    #: Chat completion cap for Ollama (OpenAI field name: max_tokens)
    ollama_max_tokens: int
    #: Run the same test discovery once before any Surgeon edits (audit pre-existing reds).
    test_baseline_before_patch: bool
    #: After Critic-approved patch, how many extra Surgeon→Critic→Tester repair rounds on failure.
    test_repair_max_retries: int
    #: Ollama chat: enable extended reasoning (`think: true`) for supported models; or "low"/"medium"/"high" for GPT-OSS.
    ollama_think: bool | str
    #: Full HTTP timeout for each Ollama /v1/chat/completions call (first load + think can be slow).
    ollama_timeout_seconds: int
    patch_strategy_snippet_enabled: bool
    patch_strategy_hunk_enabled: bool
    patch_strategy_rewrite_enabled: bool
    patch_strategy_max_diff_lines: int
    patch_strategy_max_diff_bytes: int


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
            ollama_think=_coerce_ollama_think(runtime.get("ollama_think", False)),
            ollama_timeout_seconds=max(60, int(runtime.get("ollama_timeout_seconds", 600))),
            patch_strategy_snippet_enabled=bool(runtime.get("patch_strategy_snippet_enabled", True)),
            patch_strategy_hunk_enabled=bool(runtime.get("patch_strategy_hunk_enabled", True)),
            patch_strategy_rewrite_enabled=bool(runtime.get("patch_strategy_rewrite_enabled", False)),
            patch_strategy_max_diff_lines=max(20, int(runtime.get("patch_strategy_max_diff_lines", 600))),
            patch_strategy_max_diff_bytes=max(1000, int(runtime.get("patch_strategy_max_diff_bytes", 100_000))),
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
