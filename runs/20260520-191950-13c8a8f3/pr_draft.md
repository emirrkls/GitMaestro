## Summary
Configured product bundles should ring up at a fixed bundle price, not the sum of individual SKUs.

## Steps to reproduce
1. Register products **P1** ($30) and **P2** ($20).
2. Register bundle **B1** containing both with fixed checkout price **$42**.
3. Quote bundle **B1** for cart display.

## Expected behavior
Bundle total shown to customer is **$42**.

## Actual behavior
Bundle total reflects **$50** (sum of parts).

## Scope Notes
This PR addresses the issue with bundle checkout prices and does not include unrelated fixes. For any additional changes, please create separate PRs/issues.

## Target Tests
- Widget | Gadget