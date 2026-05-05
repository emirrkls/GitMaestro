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
        ),
    )


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
