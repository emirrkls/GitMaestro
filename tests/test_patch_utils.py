import tempfile
import unittest
from pathlib import Path

from maestro.agents.json_utils import extract_first_json_value
from maestro.agents.patch_safe import (
    HunkEdit,
    RewriteEdit,
    SnippetEdit,
    apply_hunk_edits_safe,
    apply_rewrite_edits_safe,
    apply_snippet_edits_safe,
)
from maestro.policies.patch_signals import is_material_unified_diff


class PatchUtilsTests(unittest.TestCase):
    def test_extract_json_from_fence(self) -> None:
        blob = '''Here:\n```json\n{"edits":[{"path":"a.py","old_snippet":"x","new_snippet":"y"}]}\n```'''
        parsed = extract_first_json_value(blob)
        assert parsed is not None
        self.assertEqual(parsed["edits"][0]["path"], "a.py")

    def test_apply_snippet_edits_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "nested"
            repo.mkdir()
            fp = repo / "mod.py"
            fp.write_text("alpha\nBETA gamma\nbeta\n", encoding="utf-8")
            edits = [SnippetEdit(path="mod.py", old_snippet="BETA gamma", new_snippet="DELTA gamma")]
            ok, msg, diff, touched = apply_snippet_edits_safe(repo, edits)
            self.assertTrue(ok)
            self.assertEqual(msg, "ok")
            self.assertEqual(touched, ["mod.py"])
            self.assertIn("DELTA gamma", fp.read_text(encoding="utf-8"))
            self.assertTrue("@@" in diff or "--- a/mod.py" in diff)

    def test_apply_invalid_second_keeps_disk_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            fp = repo / "a.py"
            fp.write_text("one two\n", encoding="utf-8")
            edits = [
                SnippetEdit(path="a.py", old_snippet="one", new_snippet="uno"),
                SnippetEdit(path="a.py", old_snippet="missing", new_snippet="nope"),
            ]
            ok, msg, *_ = apply_snippet_edits_safe(repo, edits)
            self.assertFalse(ok)
            self.assertEqual(fp.read_text(encoding="utf-8"), "one two\n")

    def test_python_syntax_error_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            fp = repo / "mod.py"
            fp.write_text("def total():\n    return 1 + 1\n", encoding="utf-8")
            edits = [
                SnippetEdit(
                    path="mod.py",
                    old_snippet="    return 1 + 1",
                    new_snippet="return (  # broke indent\n    1 + 1",
                )
            ]
            ok, msg, *_ = apply_snippet_edits_safe(repo, edits)
            self.assertFalse(ok)
            self.assertIn("python_syntax_error", msg)
            self.assertEqual(fp.read_text(encoding="utf-8"), "def total():\n    return 1 + 1\n")

    def test_non_material_placeholder_diff(self) -> None:
        self.assertFalse(is_material_unified_diff("# Planned edits could not be applied safely: old_snippet\n"))
        self.assertTrue(is_material_unified_diff("--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"))

    def test_hunk_edit_applies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            fp = repo / "x.py"
            fp.write_text("def f():\n    return 1\n", encoding="utf-8")
            ok, status, diff, touched = apply_hunk_edits_safe(
                repo,
                [HunkEdit(path="x.py", old_block="return 1", new_block="return 2")],
                max_diff_lines=100,
                max_diff_bytes=5000,
            )
            self.assertTrue(ok)
            self.assertEqual(status, "ok")
            self.assertEqual(touched, ["x.py"])
            self.assertIn("return 2", fp.read_text(encoding="utf-8"))
            self.assertIn("@@", diff)

    def test_rewrite_respects_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            fp = repo / "x.py"
            fp.write_text("a = 1\n", encoding="utf-8")
            ok, status, *_ = apply_rewrite_edits_safe(
                repo,
                [RewriteEdit(path="x.py", new_content="a = 2\n")],
                rewrite_enabled=False,
            )
            self.assertFalse(ok)
            self.assertEqual(status, "rewrite_disabled")
            self.assertEqual(fp.read_text(encoding="utf-8"), "a = 1\n")

    def test_diff_limit_blocks_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            fp = repo / "x.py"
            fp.write_text("alpha\n", encoding="utf-8")
            ok, status, *_ = apply_snippet_edits_safe(
                repo,
                [SnippetEdit(path="x.py", old_snippet="alpha", new_snippet="beta\n" * 40)],
                max_diff_lines=5,
                max_diff_bytes=10000,
            )
            self.assertFalse(ok)
            self.assertEqual(status, "diff_lines_too_large")
            self.assertEqual(fp.read_text(encoding="utf-8"), "alpha\n")


if __name__ == "__main__":
    unittest.main()
