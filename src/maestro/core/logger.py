from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from maestro.core.message import OrchestrationEvent


class EventLogger:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.events_path = run_dir / "events.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: OrchestrationEvent) -> None:
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")

    def write_artifact(self, file_name: str, content: str) -> Path:
        path = self.run_dir / file_name
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, file_name: str, payload: dict[str, Any]) -> Path:
        path = self.run_dir / file_name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return path
