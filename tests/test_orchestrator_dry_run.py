import tempfile
import unittest
from pathlib import Path

from maestro.config.settings import load_config
from maestro.core.orchestrator import MaestroOrchestrator


class OrchestratorDryRunTests(unittest.TestCase):
    def test_orchestrator_writes_core_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
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

            self.assertTrue((state.run_dir / "events.jsonl").exists())
            self.assertTrue((state.run_dir / "score.json").exists())
            self.assertTrue((state.run_dir / "pr_draft.md").exists())

    def test_orchestrator_ambiguous_issue_escalates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
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
                        "  github_enabled: false",
                        "  test_timeout_seconds: 60",
                        '  test_command_allowlist: ["python -m unittest"]',
                    ]
                ),
                encoding="utf-8",
            )
            config = load_config(config_path=config_path)
            orchestrator = MaestroOrchestrator(repo_path=tmp_path, config=config)
            state = orchestrator.run(repo_ref="octo/demo", issue_ref="12")
            events = (state.run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"type": "escalation"', events)
            self.assertIn("ambiguous_issue_requires_clarification", events)


if __name__ == "__main__":
    unittest.main()
