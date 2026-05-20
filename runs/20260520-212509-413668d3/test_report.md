# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest discover -s tests -p test*.py
- Exit Code: 1

### stderr (baseline)
================
FAIL: test_ten_percent_off_subtotal (test_billing.TestCouponPercent.test_ten_percent_off_subtotal)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_billing.py", line 13, in test_ten_percent_off_subtotal
    self.assertEqual(result, 180.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
AssertionError: -1800.0 != 180.0

======================================================================
FAIL: test_tax_applied_after_discount (test_billing.TestTaxBase.test_tax_applied_after_discount)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_billing.py", line 28, in test_tax_applied_after_discount
    self.assertEqual(discounted, 90.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^
AssertionError: -900.0 != 90.0

======================================================================
FAIL: test_bundle_uses_fixed_price (test_catalog.TestBundlePricing.test_bundle_uses_fixed_price)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_catalog.py", line 16, in test_bundle_uses_fixed_price
    self.assertEqual(catalog.bundle_total("B1"), 42.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 50.0 != 42.0

======================================================================
FAIL: test_cancel_makes_units_available_again (test_inventory.TestCancelReleasesStock.test_cancel_makes_units_available_again)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_inventory.py", line 15, in test_cancel_makes_units_available_again
    self.assertEqual(inv.available("SKU-1"), 5)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 3 != 5

======================================================================
FAIL: test_second_order_does_not_double_points (test_loyalty.TestRepeatCheckoutPoints.test_second_order_does_not_double_points)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_loyalty.py", line 13, in test_second_order_does_not_double_points
    self.assertEqual(ledger.balance("cust-1"), 80)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 120 != 80

======================================================================
FAIL: test_credit_fully_distributed (test_orders.TestLineAllocationRounding.test_credit_fully_distributed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_orders.py", line 22, in test_credit_fully_distributed
    self.assertEqual(round(sum(shares), 2), 10.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 9.0 != 10.0

======================================================================
FAIL: test_exact_threshold_qualifies (test_shipping.TestFreeShippingThreshold.test_exact_threshold_qualifies)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212509-413668d3\workspace\tests\test_shipping.py", line 11, in test_exact_threshold_qualifies
    self.assertEqual(calc.fee_for_subtotal(50.0), 0.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 8.0 != 0.0

----------------------------------------------------------------------
Ran 8 tests in 0.004s

FAILED (failures=7, errors=1)


---

## Final test run (post-patch)
- Passed: False
- Command: N/A
- Exit Code: N/A

### stderr (final)
