# Issue Snapshot
- Repo: emirrkls/MaestroComparisonTests
- Number: 2
- URL: https://api.github.com/repos/emirrkls/MaestroComparisonTests/issues/2

## Title
Sales tax calculated on pre-discount amount

## Body
## Summary
Invoices show tax that is too high when a line-level or order-level discount is present.

## Steps to reproduce
1. Create an order with one line: **$100** merchandise.
2. Apply **10%** discount and **20%** tax rate.
3. Compare displayed tax to finance spreadsheet.

## Expected behavior
Tax should be **20% of $90** → **$18** after discount is applied.

## Actual behavior
Tax matches **20% of $100** → **$20**.