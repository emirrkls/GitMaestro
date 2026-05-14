## Bug Summary

`calculate_total()` computes wrong totals when `discount_percent` is passed as 10 for 10%.

## Reproduction

1. Run:
   `python -m unittest playground.buggy_orders.test_order_total`
2. Observe failing test: `test_applies_discount_as_percentage`

## Expected

For `subtotal=100`, `discount_percent=10`, `shipping_fee=5`, total should be `95.0`.

## Actual

Function returns a negative/incorrect value due to discount scaling bug.

## Suspected Root Cause

Discount logic likely treats percentage as fraction.

## Developer Note

This issue is intentionally planted for orchestration testing; keep patch minimal and preserve API contract (`discount_percent` is percentage input).
