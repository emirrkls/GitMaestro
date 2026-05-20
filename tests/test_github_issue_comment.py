"""Tests for ``GitHubProvider.post_issue_comment``.

We patch the underlying ``_request_raw`` / ``_request_json`` so the tests stay
hermetic (no network) but still exercise the idempotency logic, the
``GITHUB_TOKEN`` guard, and the success path.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from maestro.providers.github import GitHubProvider


class PostIssueCommentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = GitHubProvider(repo_path=Path("."), enabled=True)

    def test_skip_when_github_disabled(self) -> None:
        provider = GitHubProvider(repo_path=Path("."), enabled=False)
        result = provider.post_issue_comment("o/r", "9", "hi", idempotency_marker="m")
        self.assertIn("disabled", result.lower())

    def test_skip_when_token_missing(self) -> None:
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            result = self.provider.post_issue_comment("o/r", "9", "hi")
        self.assertIn("token", result.lower())

    def test_idempotent_skip_when_marker_present(self) -> None:
        existing = [
            {
                "body": "<!-- gitmaestro:run-id=20260520-x reason=already_resolved -->\n\nHello",
                "html_url": "https://github.com/o/r/issues/9#issuecomment-1",
            },
        ]
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False), \
                mock.patch.object(self.provider, "_request_raw", return_value=existing) as raw, \
                mock.patch.object(self.provider, "_request_json") as post:
            result = self.provider.post_issue_comment(
                "o/r",
                "9",
                "Hello again",
                idempotency_marker="reason=already_resolved",
            )
        raw.assert_called_once()
        post.assert_not_called()
        self.assertIn("idempotent", result.lower())

    def test_posts_when_marker_absent(self) -> None:
        existing: list[dict[str, str]] = [{"body": "unrelated", "html_url": "x"}]
        post_payload = {"html_url": "https://github.com/o/r/issues/9#issuecomment-99"}
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False), \
                mock.patch.object(self.provider, "_request_raw", return_value=existing), \
                mock.patch.object(self.provider, "_request_json", return_value=post_payload) as post:
            result = self.provider.post_issue_comment(
                "o/r",
                "9",
                "body",
                idempotency_marker="reason=already_resolved",
            )
        post.assert_called_once()
        self.assertEqual(result, post_payload["html_url"])

    def test_network_error_on_list_does_not_block_post(self) -> None:
        post_payload = {"html_url": "https://example/comment"}
        def _raise(**_kw: object) -> object:
            raise RuntimeError("Network error: boom")
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test"}, clear=False), \
                mock.patch.object(self.provider, "_request_raw", side_effect=_raise), \
                mock.patch.object(self.provider, "_request_json", return_value=post_payload) as post:
            result = self.provider.post_issue_comment(
                "o/r",
                "9",
                "body",
                idempotency_marker="reason=already_resolved",
            )
        post.assert_called_once()
        self.assertEqual(result, post_payload["html_url"])


if __name__ == "__main__":
    unittest.main()
