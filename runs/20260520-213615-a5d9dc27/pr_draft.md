## Summary
Warehouse API fails when planners create a second hold on the same SKU while the first hold is still open.

## Steps to reproduce
1. Seed **SKU-9** with **10** units.
2. Reserve **2** units (first hold succeeds).
3. Reserve **3** additional units on the same SKU in a separate request.

## Expected behavior
Second reservation completes; **5** units remain available; two distinct reservation identifiers are returned.

## Actual behavior
Second request raises an exception (server error) instead of completing.

TesterPassed:True

## Issue-scoped target tests
- test_two_sequential_reservations_succeed