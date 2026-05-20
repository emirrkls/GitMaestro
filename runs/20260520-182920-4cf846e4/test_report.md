# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_billing.TestTaxBase.test_tax_applied_after_discount
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_tax_applied_after_discount (tests.test_billing.TestTaxBase.test_tax_applied_after_discount)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-182920-4cf846e4\workspace\tests\test_billing.py", line 28, in test_tax_applied_after_discount
    self.assertEqual(discounted, 90.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^
AssertionError: -900.0 != 90.0

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: False
- Command: N/A
- Exit Code: N/A

### stderr (final)
