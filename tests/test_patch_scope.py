import tempfile
import unittest
from pathlib import Path

from maestro.policies.patch_scope import validate_patch_scope


_HOTEL_SYSTEM_PATCHED = '''
class HotelReservationSystem:
    def book_room(self, guest_name, room_id, checkin_str, checkout_str):
        nights = 1
        if nights <= 0:
            raise ValueError("Check-out must be after check-in")
        return "RES-1"

    def cancel_reservation(self, res_id):
        res = {"room_id": "201", "status": "ACTIVE"}
        res["status"] = "CANCELLED"
        self.rooms[res["room_id"]]["is_booked"] = False
        return True

    def generate_invoice(self, res_id, extra_charges=None):
        if extra_charges is None:
            extra_charges = []
        extra_charges = list(extra_charges) + [25.0]
        return {"total_amount": sum(extra_charges)}
'''


_THREE_HUNK_PATCH = '''--- a/hotel_system.py
+++ b/hotel_system.py
@@ -3,6 +3,8 @@
         nights = 1
+        if nights <= 0:
+            raise ValueError("Check-out must be after check-in")
         return "RES-1"
@@ -9,6 +11,7 @@
         res = {"room_id": "201", "status": "ACTIVE"}
         res["status"] = "CANCELLED"
+        self.rooms[res["room_id"]]["is_booked"] = False
         return True
@@ -13,6 +16,9 @@
-    def generate_invoice(self, res_id, extra_charges=[]):
+    def generate_invoice(self, res_id, extra_charges=None):
+        if extra_charges is None:
+            extra_charges = []
         extra_charges = list(extra_charges) + [25.0]
'''


class PatchScopeTests(unittest.TestCase):
    def test_blocks_symbols_unrelated_to_selected_target_test(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "hotel_system.py").write_text(_HOTEL_SYSTEM_PATCHED, encoding="utf-8")
            result = validate_patch_scope(
                _THREE_HUNK_PATCH,
                workspace=root,
                scout_payload={
                    "target_tests": [
                        {
                            "dotted": "test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room",
                            "label": "test_cancel_frees_room "
                            "(test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room)",
                            "match_reason": "Book a room, cancel it, then try to book it again.",
                        }
                    ]
                },
                baseline_payload={
                    "stderr": (
                        "FAIL: test_cancel_frees_room "
                        "(test_hotel_system.TestHotelReservationSystem.test_cancel_frees_room)\\n"
                        '  File "hotel_system.py", line 4, in book_room\\n'
                    )
                },
            )
            self.assertFalse(result["passed"])
            self.assertIn("generate_invoice", result["violations"])
            self.assertIn("book_room", result["touched_symbols"])
            self.assertIn("cancel_reservation", result["touched_symbols"])

    def test_allows_symbol_supported_by_invoice_target_test(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "hotel_system.py").write_text(_HOTEL_SYSTEM_PATCHED, encoding="utf-8")
            invoice_only_patch = '''--- a/hotel_system.py
+++ b/hotel_system.py
@@ -13,6 +22,9 @@
-    def generate_invoice(self, res_id, extra_charges=[]):
+    def generate_invoice(self, res_id, extra_charges=None):
+        if extra_charges is None:
+            extra_charges = []
         extra_charges = list(extra_charges) + [25.0]
'''
            result = validate_patch_scope(
                invoice_only_patch,
                workspace=root,
                scout_payload={
                    "target_tests": [
                        {
                            "dotted": "test_hotel_system.TestHotelReservationSystem.test_invoice_extra_charges_isolation",
                            "label": "test_invoice_extra_charges_isolation "
                            "(test_hotel_system.TestHotelReservationSystem.test_invoice_extra_charges_isolation)",
                            "match_reason": "Extra charges must not leak between invoices.",
                        }
                    ]
                },
                baseline_payload={"stderr": ""},
            )
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["violations"], [])


    def test_allows_symbols_from_implementation_module_matching_test_module(self) -> None:
        """``tests.test_billing`` targets may edit ``billing.apply_discount`` (generic map)."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "app"
            pkg.mkdir()
            (pkg / "billing.py").write_text(
                "def apply_discount(subtotal, discount_percent):\n"
                "    return subtotal * (1 - discount_percent)\n",
                encoding="utf-8",
            )
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_billing.py").write_text(
                "import unittest\nfrom app.billing import apply_discount\n\n"
                "class TestCoupon(unittest.TestCase):\n"
                "    def test_ten_percent(self):\n"
                "        self.assertEqual(apply_discount(200.0, 10.0), 180.0)\n",
                encoding="utf-8",
            )
            patch = """--- a/app/billing.py
+++ b/app/billing.py
@@ -1,2 +1,2 @@
 def apply_discount(subtotal, discount_percent):
-    return subtotal * (1 - discount_percent)
+    return subtotal * (1 - discount_percent / 100.0)
"""
            result = validate_patch_scope(
                patch,
                workspace=root,
                scout_payload={
                    "target_tests": [
                        {
                            "dotted": "tests.test_billing.TestCoupon.test_ten_percent",
                            "label": "test_ten_percent",
                            "match_reason": "coupon percent checkout",
                        }
                    ]
                },
                baseline_payload={"stderr": "AssertionError: -1800.0 != 180.0"},
            )
            self.assertTrue(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
