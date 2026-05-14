import unittest

from maestro.config.model_routing import ModelRouter
from maestro.config.settings import ModelConfig


class ModelRoutingTests(unittest.TestCase):
    def test_critic_uses_dedicated_model(self) -> None:
        router = ModelRouter(
            ModelConfig(
                default="gemini-2.5-flash",
                critic="llama-4-scout",
                ad_hoc_overrides={},
            )
        )
        self.assertEqual(router.model_for("Critic"), "llama-4-scout")
        self.assertEqual(router.model_for("Analyst"), "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()
