from __future__ import annotations

import subprocess
from pathlib import Path


class GitOpsProvider:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def ensure_branch(self, branch_name: str) -> str:
        if not self.is_git_repo():
            return "Current directory is not a git repository."
        exists_cmd = ["git", "rev-parse", "--verify", branch_name]
        exists = subprocess.run(
            exists_cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            shell=False,
            check=False,
        )
        if exists.returncode == 0:
            checkout = self._run(["git", "checkout", branch_name])
            return checkout
        create = self._run(["git", "checkout", "-b", branch_name])
        return create

    def commit_if_changes(self, message: str) -> str:
        if not self.is_git_repo():
            return "Current directory is not a git repository."
        status = self._run(["git", "status", "--porcelain"])
        if not status.strip():
            return "No changes to commit."
        self._run(["git", "add", "."])
        commit = self._run(["git", "commit", "-m", message])
        return commit

    def push_branch(self, branch_name: str) -> str:
        if not self.is_git_repo():
            return "Current directory is not a git repository."
        return self._run(["git", "push", "-u", "origin", branch_name])

    def is_git_repo(self) -> bool:
        result = self._run(["git", "rev-parse", "--is-inside-work-tree"])
        return result.strip().lower() == "true"

    def _run(self, cmd: list[str]) -> str:
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                shell=False,
                check=False,
            )
        except FileNotFoundError:
            return f"Command not available: {cmd[0]}"
        if completed.returncode != 0:
            return (completed.stderr or completed.stdout).strip()
        return (completed.stdout or "").strip()
