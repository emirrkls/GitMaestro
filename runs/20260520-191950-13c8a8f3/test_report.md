# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_catalog.TestBundlePricing.test_bundle_uses_fixed_price
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_bundle_uses_fixed_price (tests.test_catalog.TestBundlePricing.test_bundle_uses_fixed_price)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-191950-13c8a8f3\workspace\tests\test_catalog.py", line 16, in test_bundle_uses_fixed_price
    self.assertEqual(catalog.bundle_total("B1"), 42.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 50.0 != 42.0

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: True
- Command: python -m unittest tests.test_catalog.TestBundlePricing.test_bundle_uses_fixed_price
- Exit Code: 0

### stderr (final)
.
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
