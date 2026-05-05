from maestro.config.model_routing import ModelRouter
from maestro.config.settings import ModelConfig


def test_critic_uses_dedicated_model() -> None:
    router = ModelRouter(
        ModelConfig(
            default="gemini-2.5-flash",
            critic="llama-4-scout",
            ad_hoc_overrides={},
        )
    )
    assert router.model_for("Critic") == "llama-4-scout"
    assert router.model_for("Analyst") == "gemini-2.5-flash"
