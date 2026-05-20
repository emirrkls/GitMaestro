from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class Movement:
    agent: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    timeout: int = 120
    on_reject: dict[str, Any] | None = None


@dataclass(slots=True)
class Score:
    score_id: str
    complexity: str
    movements: list[Movement]
    escalation_policy: dict[str, Any]
    ad_hoc_allowed: bool
    ad_hoc_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "complexity": self.complexity,
            "movements": [asdict(m) for m in self.movements],
            "escalation_policy": self.escalation_policy,
            "ad_hoc_allowed": self.ad_hoc_allowed,
            "ad_hoc_budget": self.ad_hoc_budget,
        }


def build_initial_score(issue_text: str, ad_hoc_budget: int, max_retries: int) -> Score:
    lowered = issue_text.lower()
    compact = issue_text.strip()
    if compact.isdigit() and len(compact) <= 3:
        complexity = "ambiguous"
    else:
        complexity = "high" if any(k in lowered for k in ("crash", "race", "security")) else "low"
    movements = [
        Movement(agent="Maestro", task="Conductor routes specialists dynamically"),
        Movement(agent="IssueAnalyst", task="Issue decomposition and repro"),
        Movement(agent="CodeExplorer", task="Code area discovery", depends_on=["IssueAnalyst"]),
        Movement(agent="PatchAuthor", task="Minimal patch", depends_on=["CodeExplorer"]),
        Movement(
            agent="PatchReviewer",
            task="Independent patch review",
            depends_on=["PatchAuthor"],
            on_reject={"target": "PatchAuthor", "max_retry": max_retries},
        ),
        Movement(agent="TestVerifier", task="Run tests", depends_on=["PatchReviewer"]),
        Movement(agent="ReleaseScribe", task="Draft commit and PR", depends_on=["TestVerifier"]),
    ]
    if complexity == "high":
        movements.append(
            Movement(
                agent="PatchStrategist",
                task="Structured patch decomposition",
                depends_on=["CodeExplorer"],
                on_reject={"policy": "human_escalation"},
            )
        )
    if complexity == "ambiguous":
        movements.append(
            Movement(
                agent="Maestro",
                task="Clarification or escalation branch",
                depends_on=["IssueAnalyst"],
                on_reject={"policy": "human_escalation"},
            )
        )
    return Score(
        score_id=str(uuid4()),
        complexity=complexity,
        movements=movements,
        escalation_policy={"max_retry": max_retries, "on_retry_exhausted": "human_escalation"},
        ad_hoc_allowed=True,
        ad_hoc_budget=ad_hoc_budget,
    )
