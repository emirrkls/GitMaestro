## Summary
Customers report that percentage coupons produce incorrect order totals at checkout.

## Steps to reproduce
1. Start a cart with merchandise subtotal **$200**.
2. Apply a **10%** coupon at checkout.
3. Review the discounted subtotal shown to the customer.

## Expected behavior
The discounted subtotal should be **$180** (10% removed from $200).

## Actual behavior
The discounted amount is far lower than expected, as if the full coupon value were subtracted as a flat multiplier rather than a percentage.

## Scope Notes
This PR addresses the issue with incorrect total calculations for percent coupons. It does not include unrelated fixes such as updating documentation or refactoring code that are outside the scope of this specific bug fix.

## Testing
The following tests have been updated to ensure the fix works as expected:
- TestCouponPercent