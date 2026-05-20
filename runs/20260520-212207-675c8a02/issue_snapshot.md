# Issue Snapshot
- Repo: emirrkls/MaestroComparisonTests
- Number: 3
- URL: https://api.github.com/repos/emirrkls/MaestroComparisonTests/issues/3

## Title
Free shipping not applied at exact promotional threshold

## Body
## Summary
Marketing states that orders of **$50** or more ship free. Customers at exactly $50 still pay shipping.

## Steps to reproduce
1. Build a cart with merchandise subtotal **$50.00**.
2. Proceed to shipping fee calculation.

## Expected behavior
Shipping fee should be **$0**.

## Actual behavior
Standard flat shipping fee is still charged.