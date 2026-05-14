from __future__ import annotations


def calculate_total(subtotal: float, discount_percent: float, shipping_fee: float) -> float:
    """
    Calculate order total after applying discount and shipping.

    Developer note:
    Discount is expected as percentage (e.g. 10 means 10%).
    """
    if subtotal < 0:
        raise ValueError("subtotal must be non-negative")
    if shipping_fee < 0:
        raise ValueError("shipping_fee must be non-negative")
    if not (0 <= discount_percent <= 100):
        raise ValueError("discount_percent must be in [0, 100]")

    # BUG: This line treats discount_percent as a fraction (0.10)
    # while callers pass percentage (10). This can produce negative totals.
    discounted_subtotal = subtotal * (1 - (discount_percent / 100.0))
    return round(discounted_subtotal + shipping_fee, 2)
