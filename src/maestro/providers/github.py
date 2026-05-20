from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
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
            compact = issue_ref.strip()
            if compact.isdigit() and len(compact) <= 3:
                return GitHubIssue(
                    repo=repo,
                    number=compact,
                    title="",
                    body=compact,
                    url=f"https://github.com/{repo}/issues/{compact}",
                )
            return GitHubIssue(
                repo=repo,
                number=str(issue_ref),
                title=f"Issue {issue_ref}",
                body=f"Mock issue body for {issue_ref}",
                url=f"https://github.com/{repo}/issues/{issue_ref}",
            )
        issue_number = self._extract_issue_number(issue_ref)
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            return GitHubIssue(
                repo=repo,
                number=issue_number,
                title=f"Issue {issue_ref}",
                body="Fallback issue body: `GITHUB_TOKEN` is missing.",
                url=f"https://github.com/{repo}/issues/{issue_number}",
            )
        try:
            payload = self._request_json(
                method="GET",
                url=f"https://api.github.com/repos/{repo}/issues/{issue_number}",
                token=token,
            )
        except RuntimeError as exc:
            return GitHubIssue(
                repo=repo,
                number=issue_number,
                title=f"Issue {issue_ref}",
                body=f"Fallback issue body: {exc}",
                url=f"https://github.com/{repo}/issues/{issue_number}",
            )
        return GitHubIssue(
            repo=repo,
            number=str(payload.get("number", issue_number)),
            title=str(payload.get("title", f"Issue {issue_number}")),
            body=str(payload.get("body", "")),
            url=str(payload.get("url", f"https://github.com/{repo}/issues/{issue_number}")),
        )

    def post_issue_comment(
        self,
        repo: str,
        issue_number: str,
        body: str,
        *,
        idempotency_marker: str | None = None,
    ) -> str:
        """POST a comment to a GitHub issue.

        When ``idempotency_marker`` is provided, the method first lists the issue's
        existing comments and skips posting if any of them already contains the
        marker string. The marker is intended to live inside an HTML comment
        (e.g. ``<!-- gitmaestro:run-id=... -->``) so it does not show up in the
        rendered issue thread but is still searchable.

        Returns a human-readable status string. Never raises on transport errors;
        the caller treats this as best-effort feedback.
        """
        if not self.enabled:
            return "Issue comment skipped: GitHub disabled."
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            return "Issue comment skipped: `GITHUB_TOKEN` missing."
        number = self._extract_issue_number(issue_number)
        if idempotency_marker:
            try:
                existing = self._list_issue_comments(repo=repo, issue_number=number, token=token)
            except RuntimeError as exc:
                existing = []
                # Network error reading comments must not block writing; we just
                # lose the idempotency guarantee for this attempt.
                _ = exc
            for comment in existing:
                if idempotency_marker in str(comment.get("body", "")):
                    url = str(comment.get("html_url", ""))
                    return (
                        f"Issue comment skipped (idempotent): marker already present at {url}"
                        if url
                        else "Issue comment skipped (idempotent): marker already present."
                    )
        try:
            payload = self._request_json(
                method="POST",
                url=f"https://api.github.com/repos/{repo}/issues/{number}/comments",
                token=token,
                data={"body": body},
            )
        except RuntimeError as exc:
            return f"Issue comment failed: {exc}"
        return str(payload.get("html_url", "Issue comment posted."))

    def _list_issue_comments(
        self,
        *,
        repo: str,
        issue_number: str,
        token: str,
        per_page: int = 30,
    ) -> list[dict[str, object]]:
        """Fetch the most recent ``per_page`` comments for an issue (best-effort)."""
        url = (
            f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
            f"?per_page={per_page}&sort=created&direction=desc"
        )
        payload = self._request_raw(method="GET", url=url, token=token)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _request_raw(
        self,
        *,
        method: str,
        url: str,
        token: str,
        data: dict[str, object] | None = None,
    ) -> object:
        """Like ``_request_json`` but tolerates list responses (e.g. comment lists)."""
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url=url,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc

    def create_draft_pr(self, repo: str, title: str, body: str, branch: str) -> str:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            return "PR draft creation skipped: `GITHUB_TOKEN` missing."
        try:
            payload = self._request_json(
                method="POST",
                url=f"https://api.github.com/repos/{repo}/pulls",
                token=token,
                data={
                    "title": title,
                    "body": body,
                    "head": branch,
                    "base": "main",
                    "draft": True,
                },
            )
        except RuntimeError as exc:
            return f"PR draft creation skipped/failed: {exc}"
        return str(payload.get("html_url", "PR draft created."))

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

    def _request_json(
        self,
        *,
        method: str,
        url: str,
        token: str,
        data: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url=url,
            data=payload,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Network error: {exc.reason}") from exc

    @staticmethod
    def _extract_issue_number(issue_ref: str) -> str:
        compact = issue_ref.strip()
        if compact.isdigit():
            return compact
        if "/issues/" in compact:
            return compact.rsplit("/issues/", 1)[-1].split("/", 1)[0]
        return compact
