from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class GitHubIssue:
    repo: str
    number: str
    title: str
    body: str
    url: str


class GitHubProvider:
    def __init__(self, repo_path: Path, enabled: bool = True) -> None:
        self.repo_path = repo_path
        self.enabled = enabled

    def fetch_issue(self, repo: str, issue_ref: str) -> GitHubIssue:
        if not self.enabled:
            return GitHubIssue(
                repo=repo,
                number=str(issue_ref),
                title=f"Issue {issue_ref}",
                body=f"Mock issue body for {issue_ref}",
                url=f"https://github.com/{repo}/issues/{issue_ref}",
            )
        issue_number = self._extract_issue_number(issue_ref)
        if not self.is_gh_available():
            return GitHubIssue(
                repo=repo,
                number=issue_number,
                title=f"Issue {issue_ref}",
                body="Fallback issue body: `gh` CLI is not installed.",
                url=f"https://github.com/{repo}/issues/{issue_number}",
            )
        cmd = [
            "gh",
            "issue",
            "view",
            issue_number,
            "--repo",
            repo,
            "--json",
            "number,title,body,url",
        ]
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
            return GitHubIssue(
                repo=repo,
                number=issue_number,
                title=f"Issue {issue_ref}",
                body="Fallback issue body: `gh` CLI is not installed.",
                url=f"https://github.com/{repo}/issues/{issue_number}",
            )
        if completed.returncode != 0:
            return GitHubIssue(
                repo=repo,
                number=issue_number,
                title=f"Issue {issue_ref}",
                body=f"Fallback issue body: {completed.stderr.strip()}",
                url=f"https://github.com/{repo}/issues/{issue_number}",
            )
        payload = json.loads(completed.stdout or "{}")
        return GitHubIssue(
            repo=repo,
            number=str(payload.get("number", issue_number)),
            title=str(payload.get("title", f"Issue {issue_number}")),
            body=str(payload.get("body", "")),
            url=str(payload.get("url", f"https://github.com/{repo}/issues/{issue_number}")),
        )

    def create_draft_pr(self, repo: str, title: str, body: str, branch: str) -> str:
        if not self.is_gh_available():
            return "PR draft creation skipped: `gh` CLI is not installed."
        cmd = [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--draft",
            "--title",
            title,
            "--body",
            body,
            "--head",
            branch,
        ]
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
            return "PR draft creation skipped: `gh` CLI is not installed."
        if completed.returncode != 0:
            return f"PR draft creation skipped/failed: {completed.stderr.strip()}"
        return completed.stdout.strip()

    def is_gh_available(self) -> bool:
        try:
            completed = subprocess.run(
                ["gh", "--version"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                shell=False,
                check=False,
            )
            return completed.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def _extract_issue_number(issue_ref: str) -> str:
        compact = issue_ref.strip()
        if compact.isdigit():
            return compact
        if "/issues/" in compact:
            return compact.rsplit("/issues/", 1)[-1].split("/", 1)[0]
        return compact
