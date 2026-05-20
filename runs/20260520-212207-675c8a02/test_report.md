# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest discover -s tests -p test_orders.py
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_credit_fully_distributed (test_orders.TestLineAllocationRounding.test_credit_fully_distributed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-212207-675c8a02\workspace\tests\test_orders.py", line 22, in test_credit_fully_distributed
    self.assertEqual(round(sum(shares), 2), 10.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 9.0 != 10.0

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: False
- Command: N/A
- Exit Code: N/A

### stderr (final)
