# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_inventory.TestCancelReleasesStock.test_cancel_makes_units_available_again
- Exit Code: 1

### stderr (baseline)
F
======================================================================
FAIL: test_cancel_makes_units_available_again (tests.test_inventory.TestCancelReleasesStock.test_cancel_makes_units_available_again)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-184818-131bb0bc\workspace\tests\test_inventory.py", line 15, in test_cancel_makes_units_available_again
    self.assertEqual(inv.available("SKU-1"), 5)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 3 != 5

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (failures=1)


---

## Final test run (post-patch)
- Passed: False
- Command: N/A
- Exit Code: N/A

### stderr (final)
