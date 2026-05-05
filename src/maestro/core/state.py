from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maestro.core.score import Score


@dataclass(slots=True)
class RunState:
    task_id: str
    repo: str
    issue_ref: str
    run_dir: Path
    score: Score
    context: dict[str, Any] = field(default_factory=dict)
    decision_trace: list[str] = field(default_factory=list)
