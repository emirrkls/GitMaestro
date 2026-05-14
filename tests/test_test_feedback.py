import tempfile
import unittest
from pathlib import Path

from maestro.policies.test_feedback import (
    build_test_repair_feedback,
    extract_unittest_failure_labels,
    relative_test_paths_mentioned,
)


class TestFeedbackTests(unittest.TestCase):
    def test_extract_failure_labels(self) -> None:
        stderr = "FAIL: test_cart.TestShoppingCart.test_empty (test_cart.py)\nERROR: test_cart.TestShoppingCart.x\n"
        labels = extract_unittest_failure_labels(stderr)
        self.assertIn("test_cart.TestShoppingCart.test_empty (test_cart.py)", labels)
        self.assertIn("test_cart.TestShoppingCart.x", labels)

    def test_relative_paths_from_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "test_cart.py").write_text("# t\n", encoding="utf-8")
            stderr = r'File "C:\proj\test_cart.py", line 21, in test_empty'
            found = relative_test_paths_mentioned(stderr, root)
            self.assertEqual(found, ["test_cart.py"])

    def test_build_repair_feedback_includes_baseline_note(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fb = build_test_repair_feedback(
                {"passed": False, "command": "python -m unittest x", "exit_code": 1, "stderr": "baseline err"},
                {"command": "python -m unittest x", "exit_code": 1, "stderr": "FAIL: a.b.c\n"},
                workspace=root,
            )
            self.assertIn("Pre-patch baseline", fb)
            self.assertIn("ALREADY FAILING", fb)
            self.assertIn("FAIL: a.b.c", fb)


if __name__ == "__main__":
    unittest.main()
