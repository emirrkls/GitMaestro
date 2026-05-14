import tempfile
import unittest
from pathlib import Path

from maestro.agents.patch_safe import SnippetEdit
from maestro.agents.surgeon import _single_line_fallback_edits, _synthesize_hunks_from_snippets


class SurgeonFallbackTests(unittest.TestCase):
    def test_rejects_multiline_edit_for_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            edits = [
                SnippetEdit(
                    path="a.py",
                    old_snippet="x = 1\ny = 2",
                    new_snippet="x = 2\ny = 2",
                )
            ]
            self.assertEqual(_single_line_fallback_edits(root, edits), [])

    def test_accepts_true_single_line_edit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            edits = [SnippetEdit(path="a.py", old_snippet="x = 1", new_snippet="x = 2")]
            out = _single_line_fallback_edits(root, edits)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].old_snippet, "x = 1")
            self.assertEqual(out[0].new_snippet, "x = 2")

    def test_synthesizes_hunk_from_trimmed_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.py").write_text("x = 1   \ny = 2\n", encoding="utf-8")
            edits = [SnippetEdit(path="a.py", old_snippet="x = 1\ny = 2\n", new_snippet="x = 2\ny = 2\n")]
            hunks = _synthesize_hunks_from_snippets(root, edits)
            self.assertEqual(len(hunks), 1)
            self.assertIn("x = 1", hunks[0].old_block)
            self.assertEqual(hunks[0].new_block, "x = 2\ny = 2\n")


if __name__ == "__main__":
    unittest.main()
