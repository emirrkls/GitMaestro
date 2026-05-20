# Issue Snapshot
- Repo: emirrkls/MaestroComparisonTests
- Number: 5
- URL: https://api.github.com/repos/emirrkls/MaestroComparisonTests/issues/5

## Title
Loyalty balance jumps after repeat purchase

## Body
## Summary
Returning customers accumulate loyalty points faster than policy allows.

## Steps to reproduce
1. Customer **cust-1** completes order **order-a** with **$40** paid (1 point per dollar policy).
2. Same customer completes **order-b**, also **$40** paid.
3. Inspect loyalty balance.

## Expected behavior
Balance should be **80** points total.

## Actual behavior
Balance exceeds **80** on the second order.