from datetime import date, timedelta

from lateness import GRACE_DAYS, WARNING_DAYS, classify_lateness


def test_lateness_thresholds_are_consistent():
    requested = date(2026, 9, 1)

    assert classify_lateness(requested + timedelta(days=GRACE_DAYS), requested) == (
        GRACE_DAYS, "on_time", False
    )
    assert classify_lateness(requested + timedelta(days=GRACE_DAYS + 1), requested) == (
        GRACE_DAYS + 1, "warning", True
    )
    assert classify_lateness(requested + timedelta(days=WARNING_DAYS + 1), requested) == (
        WARNING_DAYS + 1, "critical", True
    )


def test_missing_dates_have_no_lateness_classification():
    assert classify_lateness(None, date(2026, 9, 1)) == (None, None, None)
    assert classify_lateness(date(2026, 9, 8), None) == (None, None, None)
