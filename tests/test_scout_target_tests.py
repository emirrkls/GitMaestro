"""Scout's AST harvester + target_test selection — issue-scoped test discovery."""

import json
import tempfile
import unittest
from pathlib import Path

from maestro.agents.scout import CodeExplorerAgent
from maestro.providers.llm.base import LLMProvider, LLMResponse


_HOTEL_TESTS_SOURCE = '''
import unittest
from hotel_system import HotelReservationSystem


class TestHotelReservationSystem(unittest.TestCase):
    def setUp(self):
        self.hotel = HotelReservationSystem()

    def test_negative_nights_validation(self):
        # Booking with checkout BEFORE checkin should raise an error, not create a negative invoice
        pass

    def test_cancel_frees_room(self):
        """Book a room, cancel it, then try to book it again."""
        pass

    def test_invoice_extra_charges_isolation(self):
        # Generate an invoice for Dave
        self.assertEqual(150.0, 125.0, "Extra charges leaked from previous invoice!")
'''


class _CannedLLM(LLMProvider):
    """Test double that returns a scripted JSON payload regardless of prompt."""

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.last_prompt: str = ""

    def complete(self, *, model: str, prompt: str) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(text=self.response_text, model=model)


class ScoutTargetSelectionTests(unittest.TestCase):
    def _scaffold(self, root: Path) -> None:
        (root / "test_hotel_system.py").write_text(_HOTEL_TESTS_SOURCE, encoding="utf-8")
        (root / "hotel_system.py").write_text("# stub\n", encoding="utf-8")

    def test_harvest_extracts_class_and_function_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._scaffold(root)
            scout = CodeExplorerAgent(_CannedLLM("not json"), "test-model")
            result = scout.run({"issue_text": "anything", "repo_path": str(root)})
            harvested = result.payload["harvested_tests"]
            names = {item["name"] for item in harvested}
            self.assertEqual(
                names,
                {
                    "test_negative_nights_validation",
                    "test_cancel_frees_room",
                    "test_invoice_extra_charges_isolation",
                },
            )
            # Class binding is preserved so unittest dotted ids are reconstructable.
            for record in harvested:
                self.assertEqual(record["class"], "TestHotelReservationSystem")
                self.assertTrue(record["dotted"].endswith(record["name"]))
            # Docstring AND inline-comment fallbacks both work.
            by_name = {r["name"]: r for r in harvested}
            self.assertIn("Book a room, cancel it", by_name["test_cancel_frees_room"]["docstring"])
            self.assertIn(
                "Booking with checkout BEFORE checkin",
                by_name["test_negative_nights_validation"]["hint"],
            )
            self.assertIn(
                "Extra charges leaked from previous invoice",
                by_name["test_invoice_extra_charges_isolation"]["body_text"],
            )

    def test_llm_target_selection_filters_hallucinations(self) -> None:
        """LLM picks real tests + tries to invent one — Scout must drop the fake."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._scaffold(root)
            payload = json.dumps(
                {
                    "impact_zones": "billing logic",
                    "target_tests": [
                        {
                            "dotted": "test_hotel_system.TestHotelReservationSystem.test_invoice_extra_charges_isolation",
                            "label": "test_invoice_extra_charges_isolation",
                            "match_reason": "Issue is about overcharging on invoices",
                            "confidence": "high",
                        },
                        {
                            "dotted": "test_hotel_system.TestHotelReservationSystem.test_fictional_overcharge",
                            "label": "Hallucinated test that does not exist",
                            "match_reason": "hallucinated",
                            "confidence": "high",
                        },
                    ],
                }
            )
            scout = CodeExplorerAgent(_CannedLLM(payload), "test-model")
            result = scout.run(
                {
                    "issue_text": "Customers complaining about overcharging on bills.",
                    "repo_path": str(root),
                    "analysis": {
                        "expected_behavior_changes": [
                            "Invoices must not double-bill cleaning fees",
                        ]
                    },
                }
            )
            target_names = {t["dotted"].rsplit(".", 1)[-1] for t in result.payload["target_tests"]}
            self.assertIn("test_invoice_extra_charges_isolation", target_names)
            self.assertNotIn("test_fictional_overcharge", target_names)
            self.assertEqual(result.payload["target_selection_source"], "llm")

    def test_heuristic_fallback_picks_overcharge_test_for_billing_issue(self) -> None:
        """When LLM output is unparseable, keyword heuristic still picks the right test."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._scaffold(root)
            scout = CodeExplorerAgent(_CannedLLM("not valid json {{{"), "test-model")
            result = scout.run(
                {
                    "issue_text": (
                        "Customers complaining about getting overcharged on their invoice "
                        "bills with extra charges they never used."
                    ),
                    "repo_path": str(root),
                }
            )
            self.assertEqual(result.payload["target_selection_source"], "heuristic")
            dotted = [t["dotted"] for t in result.payload["target_tests"]]
            self.assertTrue(
                any(d.endswith("test_invoice_extra_charges_isolation") for d in dotted),
                f"expected invoice test in heuristic targets, got: {dotted}",
            )

    def test_explicit_empty_llm_targets_can_use_strong_semantic_fallback(self) -> None:
        """Financial-report wording should map to invoice/charge tests even if LLM is unsure."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._scaffold(root)
            payload = json.dumps(
                {
                    "impact_zones": "financial reports",
                    "target_tests": [],
                    "out_of_scope_tests": [
                        "test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room",
                        "test_hotel_system.TestHotelReservationSystem.test_invoice_extra_charges_isolation",
                    ],
                }
            )
            scout = CodeExplorerAgent(_CannedLLM(payload), "test-model")
            result = scout.run(
                {
                    "issue_text": "Financial report shows a weird total for a recent stay.",
                    "repo_path": str(root),
                }
            )
            self.assertEqual(result.payload["target_selection_source"], "semantic_fallback")
            self.assertFalse(result.payload["target_selection_blocking"])
            dotted = [t["dotted"] for t in result.payload["target_tests"]]
            self.assertEqual(
                dotted,
                ["test_hotel_system.TestHotelReservationSystem.test_invoice_extra_charges_isolation"],
            )

    def test_explicit_empty_llm_targets_still_blocks_without_strong_semantics(self) -> None:
        """If LLM says it is unsure and no strong domain match exists, block safely."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._scaffold(root)
            payload = json.dumps(
                {
                    "impact_zones": "unclear area",
                    "target_tests": [],
                    "out_of_scope_tests": [
                        "test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room",
                    ],
                }
            )
            scout = CodeExplorerAgent(_CannedLLM(payload), "test-model")
            result = scout.run(
                {
                    "issue_text": "Something odd happens in a recent stay.",
                    "repo_path": str(root),
                }
            )
            self.assertEqual(result.payload["target_tests"], [])
            self.assertEqual(result.payload["target_selection_source"], "llm_empty")
            self.assertTrue(result.payload["target_selection_blocking"])

    def test_llm_target_ids_with_catalog_hint_suffix_are_accepted(self) -> None:
        """Models echo ``dotted :: hint`` from the catalog; Scout must keep the real id."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._scaffold(root)
            payload = json.dumps(
                {
                    "impact_zones": "billing",
                    "target_tests": [
                        {
                            "dotted": (
                                "test_hotel_system.TestHotelReservationSystem"
                                ".test_invoice_extra_charges_isolation :: Extra charges leaked"
                            ),
                            "label": "invoice isolation",
                            "match_reason": "matches issue",
                            "confidence": "high",
                        }
                    ],
                }
            )
            scout = CodeExplorerAgent(_CannedLLM(payload), "test-model")
            result = scout.run(
                {
                    "issue_text": "Extra charges leak between invoices.",
                    "repo_path": str(root),
                }
            )
            self.assertEqual(result.payload["target_selection_source"], "llm")
            self.assertFalse(result.payload["target_selection_blocking"])
            dotted = result.payload["target_tests"][0]["dotted"]
            self.assertTrue(dotted.endswith("test_invoice_extra_charges_isolation"))

    def test_no_tests_present_returns_empty_targets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "hotel_system.py").write_text("# stub\n", encoding="utf-8")
            scout = CodeExplorerAgent(_CannedLLM("not json"), "test-model")
            result = scout.run({"issue_text": "anything", "repo_path": str(root)})
            self.assertEqual(result.payload["target_tests"], [])
            self.assertEqual(result.payload["target_selection_source"], "none")


if __name__ == "__main__":
    unittest.main()
