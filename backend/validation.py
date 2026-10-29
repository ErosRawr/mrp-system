"""
Input validation shared by the API endpoints.

Every check raises HTTPException(400) with a message that says what to fix.
The rules live here, in one place, so create and update endpoints cannot
drift apart.
"""

import math
from datetime import date

from fastapi import HTTPException

MIN_YEAR, MAX_YEAR = 1970, 2200
MAX_ORDER_TONS = 1_000_000           # one order; far above any realistic request
MAX_TEAM_MONTHLY_TONS = 100_000_000  # catches a typo like an extra run of zeros


def bad(message: str):
    raise HTTPException(400, message)


def clean_text(value, field: str, max_length: int, required: bool = True):
    """
    Trims the text and rejects blank values, control characters, angle
    brackets and over-long values. Returns the cleaned text (or None for an
    optional field left empty).

    The angle-bracket rule is defense in depth: the page must still escape
    everything it renders, but there is no reason to store markup in a name.
    """
    text = (value or "").strip()
    if not text:
        if required:
            bad(f"{field} cannot be empty")
        return None
    if len(text) > max_length:
        bad(f"{field} is too long ({len(text)} characters, the limit is {max_length})")
    if any(ord(ch) < 32 for ch in text):
        bad(f"{field} cannot contain control characters")
    if "<" in text or ">" in text:
        bad(f"{field} cannot contain < or >")
    return text


def require_finite(value: float, field: str) -> float:
    """Rejects nan and inf: every range check passes or fails oddly on them,
    and a stored nan makes whole endpoints return 500."""
    if not math.isfinite(value):
        bad(f"{field} must be a normal number, not nan or inf")
    return value


def require_year(year: int, field: str = "year") -> int:
    if not (MIN_YEAR <= year <= MAX_YEAR):
        bad(f"{field} must be a realistic calendar year ({MIN_YEAR}-{MAX_YEAR})")
    return year


def require_month(month: int, field: str = "month") -> int:
    if not (1 <= month <= 12):
        bad(f"{field} must be between 1 and 12")
    return month


def require_week(year: int, week_number: int) -> int:
    """Week numbers are ISO weeks: most years have 52, some have 53."""
    weeks_in_year = date(year, 12, 28).isocalendar()[1]
    if not (1 <= week_number <= weeks_in_year):
        bad(f"week_number must be between 1 and {weeks_in_year} (ISO weeks; {year} has {weeks_in_year})")
    return week_number


def require_order_tons(quantity: float, field: str = "quantity_requested") -> float:
    require_finite(quantity, field)
    if quantity <= 0:
        bad(f"{field} must be greater than 0")
    if quantity > MAX_ORDER_TONS:
        bad(f"{field} is {quantity:,.0f} t, above the {MAX_ORDER_TONS:,} t limit for a single order -- check for an extra zero")
    return quantity
