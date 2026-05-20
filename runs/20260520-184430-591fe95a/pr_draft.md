## Summary
Marketing states that orders of **$50** or more ship free. Customers at exactly $50 still pay shipping.

## Steps to reproduce
1. Build a cart with merchandise subtotal **$50.00**.
2. Proceed to shipping fee calculation.

## Expected behavior
Shipping fee should be **$0**.

## Actual behavior
Standard flat shipping fee is still charged.

## Scope Notes
This PR addresses the issue of free shipping not being applied at exactly $50. Other unrelated fixes have been noted and should be addressed in separate PRs/issues:
- Fix typo in shipping calculation logic
- Update documentation for free shipping threshold

**TesterPassed:** True

## Issue-scoped target tests
- TestFreeShippingThreshold