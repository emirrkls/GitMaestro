from __future__ import annotations

import unittest

from playground.buggy_orders.order_total import calculate_total


class OrderTotalTests(unittest.TestCase):
    def test_applies_discount_as_percentage(self) -> None:
        total = calculate_total(subtotal=100.0, discount_percent=10.0, shipping_fee=5.0)
        self.assertEqual(total, 95.0)

    def test_zero_discount(self) -> None:
        total = calculate_total(subtotal=100.0, discount_percent=0.0, shipping_fee=5.0)
        self.assertEqual(total, 105.0)


if __name__ == "__main__":
    unittest.main()
