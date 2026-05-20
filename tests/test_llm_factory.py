import unittest

from maestro.config.settings import RuntimeConfig
from maestro.providers.llm.factory import build_llm_provider
from maestro.providers.llm.ollama_provider import OllamaProvider


def _rt(**kwargs: object) -> RuntimeConfig:
    base = dict(
        mock_llm=False,
        allow_commit=False,
        allow_push=False,
        max_retries=1,
        ad_hoc_budget=0,
        test_timeout_seconds=60,
        test_command_allowlist=["python -m unittest"],
        github_enabled=False,
        allow_pr_draft=False,
        branch_prefix="test",
        llm_backend="cloud",
        ollama_base_url="http://127.0.0.1:11434/v1",
        ollama_max_tokens=8192,
        test_baseline_before_patch=True,
        test_repair_max_retries=2,
        require_fix_on_red_baseline=True,
        strict_scope_mode=True,
        require_target_tests=False,
        post_issue_feedback_comments=False,
        critic_final_retry_min_confidence=0.92,
        agentic_fatigue_escalation_enabled=True,
        agentic_fatigue_min_rejects=3,
        agentic_fatigue_compromise_max_confidence=0.78,
        agentic_fatigue_confidence_drop_min=0.18,
        agentic_fatigue_require_both_signals=True,
        agentic_fatigue_require_explicit_confidence=True,
        ollama_think=False,
        ollama_timeout_seconds=600,
        nvidia_base_url="https://integrate.api.nvidia.com/v1",
        nvidia_timeout_seconds=90,
        nvidia_max_tokens=4096,
        nvidia_rpm_limit=30,
        nvidia_rpm_overrides={},
        patch_strategy_snippet_enabled=True,
        patch_strategy_hunk_enabled=True,
        patch_strategy_rewrite_enabled=False,
        patch_strategy_max_diff_lines=600,
        patch_strategy_max_diff_bytes=100000,
        maestro_max_conductor_steps=48,
    )
    base.update(kwargs)
    return RuntimeConfig(**base)  # type: ignore[arg-type]


class LlmFactoryTests(unittest.TestCase):
    def test_mock_short_circuits(self) -> None:
        p = build_llm_provider(_rt(mock_llm=True))
        self.assertEqual(type(p).__name__, "MockLLMProvider")

    def test_ollama_backend(self) -> None:
        p = build_llm_provider(_rt(llm_backend="ollama"))
        self.assertIsInstance(p, OllamaProvider)

    def test_ollama_backend_passes_think(self) -> None:
        p = build_llm_provider(_rt(llm_backend="ollama", ollama_think=True))
        self.assertIsInstance(p, OllamaProvider)
        self.assertTrue(getattr(p, "think", False))

    def test_hybrid_backend_builds(self) -> None:
        p = build_llm_provider(_rt(llm_backend="hybrid"))
        self.assertEqual(type(p).__name__, "PrefixHybridProvider")


if __name__ == "__main__":
    unittest.main()
