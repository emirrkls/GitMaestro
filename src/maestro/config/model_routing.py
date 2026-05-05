from __future__ import annotations

from maestro.config.settings import ModelConfig


class ModelRouter:
    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def model_for(self, agent_name: str) -> str:
        if agent_name.lower() == "critic":
            return self.config.critic
        return self.config.ad_hoc_overrides.get(agent_name, self.config.default)
