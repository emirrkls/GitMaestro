# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_shipping.TestFreeShippingThreshold.test_exact_threshold_qualifies
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_exact_threshold_qualifies (tests.test_shipping.TestFreeShippingThreshold.test_exact_threshold_qualifies)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-210829-23eff1b4\workspace\tests\test_shipping.py", line 11, in test_exact_threshold_qualifies
    self.assertEqual(calc.fee_for_subtotal(50.0), 0.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 8.0 != 0.0

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: True
- Command: python -m unittest tests.test_shipping.TestFreeShippingThreshold.test_exact_threshold_qualifies
- Exit Code: 0

### stderr (final)
.
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
