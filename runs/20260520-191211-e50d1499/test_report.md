# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_loyalty.TestRepeatCheckoutPoints.test_second_order_does_not_double_points
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_second_order_does_not_double_points (tests.test_loyalty.TestRepeatCheckoutPoints.test_second_order_does_not_double_points)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-191211-e50d1499\workspace\tests\test_loyalty.py", line 13, in test_second_order_does_not_double_points
    self.assertEqual(ledger.balance("cust-1"), 80)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 120 != 80

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: True
- Command: python -m unittest tests.test_loyalty.TestRepeatCheckoutPoints.test_second_order_does_not_double_points
- Exit Code: 0

### stderr (final)
.
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
