from __future__ import annotations

from maestro.config.settings import ModelConfig

_LEGACY_AGENT_KEYS: dict[str, str] = {
    "Analyst": "IssueAnalyst",
    "Scout": "CodeExplorer",
    "Surgeon": "PatchAuthor",
    "Critic": "PatchReviewer",
    "PatchPlanner": "PatchStrategist",
    "Tester": "TestVerifier",
    "Scribe": "ReleaseScribe",
}

_REVIEWER_NAMES = frozenset({"critic", "patchreviewer", "patch reviewer"})


class ModelRouter:
    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    def model_for(self, agent_name: str) -> str:
        if agent_name.lower().replace(" ", "") in _REVIEWER_NAMES or agent_name == "PatchReviewer":
            return self.config.critic
        if agent_name in self.config.ad_hoc_overrides:
            return self.config.ad_hoc_overrides[agent_name]
        legacy = _LEGACY_AGENT_KEYS.get(agent_name)
        if legacy and legacy in self.config.ad_hoc_overrides:
            return self.config.ad_hoc_overrides[legacy]
        return self.config.default
