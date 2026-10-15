"""
Single definition of "late" for the whole system.

Delivery dates are week-ending Sundays (see planning._week_end_date), so a
small grace period keeps an order that lands in the requested week from
being flagged. Change the thresholds here and every view follows.
"""

GRACE_DAYS = 7      # up to this many days after the requested date: on time
WARNING_DAYS = 14   # up to this many days: warning; beyond it: critical


def classify_lateness(calculated_delivery_date, requested_delivery_date):
    """
    Returns (days_late, lateness_status, is_late).
    All three are None when either date is missing (not planned yet, or
    no requested date to compare against).
    """
    if calculated_delivery_date is None or requested_delivery_date is None:
        return None, None, None

    days_late = (calculated_delivery_date - requested_delivery_date).days

    if days_late <= GRACE_DAYS:
        status = "on_time"
    elif days_late <= WARNING_DAYS:
        status = "warning"
    else:
        status = "critical"

    return days_late, status, days_late > GRACE_DAYS
