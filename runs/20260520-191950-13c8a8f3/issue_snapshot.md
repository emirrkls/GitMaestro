# Issue Snapshot
- Repo: emirrkls/MaestroComparisonTests
- Number: 6
- URL: https://api.github.com/repos/emirrkls/MaestroComparisonTests/issues/6

## Title
Bundle checkout price ignores promotional bundle rate

## Body
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