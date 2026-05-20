# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_orders.TestLineAllocationRounding.test_credit_fully_distributed
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_credit_fully_distributed (tests.test_orders.TestLineAllocationRounding.test_credit_fully_distributed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-195327-d620219a\workspace\tests\test_orders.py", line 22, in test_credit_fully_distributed
    self.assertEqual(round(sum(shares), 2), 10.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 9.0 != 10.0

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: False
- Command: python -m unittest tests.test_orders.TestLineAllocationRounding.test_credit_fully_distributed
- Exit Code: 1

### stderr (final)
F
======================================================================
FAIL: test_credit_fully_distributed (tests.test_orders.TestLineAllocationRounding.test_credit_fully_distributed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-195327-d620219a\workspace\tests\test_orders.py", line 22, in test_credit_fully_distributed
    self.assertEqual(round(sum(shares), 2), 10.0)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 9.99 != 10.0

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)
