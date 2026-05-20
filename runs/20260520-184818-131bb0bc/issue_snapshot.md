# Issue Snapshot
- Repo: emirrkls/MaestroComparisonTests
- Number: 4
- URL: https://api.github.com/repos/emirrkls/MaestroComparisonTests/issues/4

## Title
Cancelled warehouse hold does not return stock to sellable pool

## Body
## Summary
After cancelling a reservation, the storefront still shows reduced availability.

## Steps to reproduce
1. Seed SKU **SKU-1** with **5** units available.
2. Reserve **2** units for a pending order.
3. Cancel that reservation.
4. Query available quantity for **SKU-1**.

## Expected behavior
Available quantity returns to **5**.

## Actual behavior
Available quantity remains **3** as if the hold were still active.