from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


class TestRunner:
    def __init__(self, repo_path: Path, allowed_prefixes: list[str], timeout_seconds: int = 120) -> None:
        self.repo_path = repo_path
        self.allowed_prefixes = allowed_prefixes
        self.timeout_seconds = timeout_seconds

    def run(self, command: str) -> dict[str, object]:
        if not self._is_allowed(command):
            return {
                "passed": False,
                "exit_code": 126,
                "stdout": "",
                "stderr": f"Command not allowed by whitelist: {command}",
            }
        args = shlex.split(command, posix=False)
        try:
            completed = subprocess.run(
                args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
            return {
                "passed": completed.returncode == 0,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        except subprocess.TimeoutExpired:
            return {"passed": False, "exit_code": 124, "stdout": "", "stderr": "Test command timed out"}

    def _is_allowed(self, command: str) -> bool:
        normalized = command.strip().lower()
        return any(normalized.startswith(prefix.lower()) for prefix in self.allowed_prefixes)
