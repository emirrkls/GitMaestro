from pathlib import Path

from maestro.config.settings import load_config
from maestro.core.orchestrator import MaestroOrchestrator


def test_orchestrator_writes_core_artifacts(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "models:",
                "  default: gemini-2.5-flash",
                "  critic: llama-4-scout",
                "  ad_hoc_overrides: {}",
                "runtime:",
                "  mock_llm: true",
                "  allow_commit: false",
                "  allow_push: false",
                "  max_retries: 2",
                "  ad_hoc_budget: 1",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(config_path=config_path)
    orchestrator = MaestroOrchestrator(repo_path=tmp_path, config=config)
    state = orchestrator.run(repo_ref="octo/demo", issue_ref="security-crash-1")

    assert (state.run_dir / "events.jsonl").exists()
    assert (state.run_dir / "score.json").exists()
    assert (state.run_dir / "pr_draft.md").exists()


def test_orchestrator_ambiguous_issue_escalates(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "models:",
                "  default: gemini-2.5-flash",
                "  critic: llama-4-scout",
                "  ad_hoc_overrides: {}",
                "runtime:",
                "  mock_llm: true",
                "  allow_commit: false",
                "  allow_push: false",
                "  max_retries: 2",
                "  ad_hoc_budget: 1",
                "  test_timeout_seconds: 60",
                "  test_command_allowlist: [\"python -m unittest\"]",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(config_path=config_path)
    orchestrator = MaestroOrchestrator(repo_path=tmp_path, config=config)
    state = orchestrator.run(repo_ref="octo/demo", issue_ref="12")
    events = (state.run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"type": "escalation"' in events
    assert "ambiguous_issue_requires_clarification" in events
