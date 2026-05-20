import tempfile
import unittest
from pathlib import Path

from maestro.providers.test_runner import TestRunner


class TestRunnerScopeTests(unittest.TestCase):
    def test_target_dotted_ids_are_grouped_into_one_unittest_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            runner = TestRunner(
                repo_path=Path(td),
                allowed_prefixes=["python -m unittest"],
            )
            commands = runner.issue_scoped_commands(
                {
                    "scout": {
                        "target_test_dotted": [
                            "test_hotel.TestHotel.test_invoice",
                            "test_hotel.TestHotel.test_cancel",
                            "test_hotel.TestHotel.test_invoice",
                        ]
                    }
                }
            )
            self.assertEqual(
                commands,
                [
                    "python -m unittest "
                    "test_hotel.TestHotel.test_invoice "
                    "test_hotel.TestHotel.test_cancel"
                ],
            )


if __name__ == "__main__":
    unittest.main()
