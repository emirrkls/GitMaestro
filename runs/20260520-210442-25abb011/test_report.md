# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_billing.TestCouponPercent.test_ten_percent_off_subtotal
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_ten_percent_off_subtotal (tests.test_billing.TestCouponPercent.test_ten_percent_off_subtotal)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-210442-25abb011\workspace\tests\test_billing.py", line 13, in test_ten_percent_off_subtotal
    self.assertEqual(result, 180.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
AssertionError: -1800.0 != 180.0

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: True
- Command: python -m unittest tests.test_billing.TestCouponPercent.test_ten_percent_off_subtotal
- Exit Code: 0

### stderr (final)
.
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
