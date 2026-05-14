# Buggy Orders Playground

This folder intentionally contains a bug for end-to-end orchestration testing.

## Scenario

- Function: `calculate_total(subtotal, discount_percent, shipping_fee)`
- Expected: `discount_percent` is a percentage (10 means 10%)
- Actual bug: discount is treated as a fraction (0.10), causing incorrect totals

## Repro

```bash
python -m unittest playground.buggy_orders.test_order_total
```

Expected failing test:

- `test_applies_discount_as_percentage`
