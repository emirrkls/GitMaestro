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
This PR addresses the issue where free shipping was not applied at the exact promotional threshold of $50. No other unrelated fixes are included in this PR.

## Target Tests
- TestFreeShippingThreshold