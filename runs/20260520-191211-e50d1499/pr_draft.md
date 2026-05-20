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

## Scope Notes
This PR addresses the issue of incorrect loyalty point accumulation for repeat purchases. It does not include unrelated fixes such as updating the documentation or refactoring code, which should be addressed in separate PRs/issues.

## Testing
TesterPassed:True
Issue-scoped target tests:
- TestRepeatCheckoutPoints