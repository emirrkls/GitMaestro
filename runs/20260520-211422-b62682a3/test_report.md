# Test Report

## Pre-patch baseline
- Passed: False
- Command: python -m unittest tests.test_inventory.TestReserveSameSkuTwice.test_two_sequential_reservations_succeed
- Exit Code: 1

### stderr (baseline)
E
======================================================================
ERROR: test_two_sequential_reservations_succeed (tests.test_inventory.TestReserveSameSkuTwice.test_two_sequential_reservations_succeed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-211422-b62682a3\workspace\tests\test_inventory.py", line 23, in test_two_sequential_reservations_succeed
    second = inv.reserve("SKU-9", 3)
  File "C:\Users\Emir\Desktop\GitMaestro\runs\20260520-211422-b62682a3\workspace\retailflow\inventory.py", line 39, in reserve
    return self._records[entry.reservation_id]
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^
KeyError: 'b924e8ac-de18-43fb-9332-a2787aaf331c'

----------------------------------------------------------------------
Ran 1 test in 0.001s

FAILED (errors=1)


---

## Final test run (post-patch)
- Passed: True
- Command: python -m unittest tests.test_inventory.TestReserveSameSkuTwice.test_two_sequential_reservations_succeed
- Exit Code: 0

### stderr (final)
.
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
