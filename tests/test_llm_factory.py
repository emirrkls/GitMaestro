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
        ollama_think=False,
        ollama_timeout_seconds=600,
        patch_strategy_snippet_enabled=True,
        patch_strategy_hunk_enabled=True,
        patch_strategy_rewrite_enabled=False,
        patch_strategy_max_diff_lines=600,
        patch_strategy_max_diff_bytes=100000,
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


if __name__ == "__main__":
    unittest.main()
