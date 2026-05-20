# Issue Snapshot
- Repo: emirrkls/MaestroComparisonTests
- Number: 8
- URL: https://api.github.com/repos/emirrkls/MaestroComparisonTests/issues/8

## Title
Promotional credit split leaves unreconciled cents

## Body
## Summary
When spreading a fixed store credit across multiple order lines, the allocated parts do not add up to the full credit amount.

## Steps to reproduce
1. Create an order with three lines priced **33.33**, **33.33**, and **33.34**.
2. Allocate **$10** promotional credit across lines.
3. Sum the per-line credit shares.

## Expected behavior
Shares sum to exactly **$10.00** across three lines.

## Actual behavior
Sum of shares is less than **$10.00** (lost fractional cents).