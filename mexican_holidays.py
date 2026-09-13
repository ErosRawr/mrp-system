"""
Mexican federal holidays (Ley Federal del Trabajo, Art. 74), computed in
pure Python -- no external API or internet dependency, so this works
offline and won't break a demo if network access is unavailable.

Fixed-date holidays and the "nth weekday of month" holidays are both
covered. The sexenio transfer day (Oct 1, every 6 years starting 2024)
is included since it's a mandatory holiday but only in transition years.
"""

from datetime import date, timedelta


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """
    Returns the date of the nth occurrence of `weekday` (0=Monday) in the
    given month/year. E.g. n=1, weekday=0 (Monday), month=2 -> first
    Monday of February.
    """
    d = date(year, month, 1)
    days_until_weekday = (weekday - d.weekday()) % 7
    first_occurrence = d + timedelta(days=days_until_weekday)
    return first_occurrence + timedelta(weeks=n - 1)


def get_mexican_holidays(year: int):
    """
    Returns a list of (date, description) tuples for all mandatory
    Mexican federal holidays in the given year.
    """
    holidays = [
        (date(year, 1, 1), "Año Nuevo"),
        (_nth_weekday_of_month(year, 2, 0, 1), "Día de la Constitución"),  # 1st Monday of Feb
        (_nth_weekday_of_month(year, 3, 0, 3), "Natalicio de Benito Juárez"),  # 3rd Monday of Mar
        (date(year, 5, 1), "Día del Trabajo"),
        (date(year, 9, 16), "Día de la Independencia"),
        (_nth_weekday_of_month(year, 11, 0, 3), "Día de la Revolución"),  # 3rd Monday of Nov
        (date(year, 12, 25), "Navidad"),
    ]

    # Presidential transition day: Oct 1, every 6 years, only in the year
    # a new federal administration takes office (2024, 2030, 2036, ...).
    if (year - 2024) % 6 == 0:
        holidays.append((date(year, 10, 1), "Transmisión del Poder Ejecutivo Federal"))

    return sorted(holidays, key=lambda h: h[0])


def get_holiday_week_impact(year: int, working_days_per_week: int = 5):
    """
    Converts each holiday date into its ISO (year, week_number), and
    returns a dict mapping (iso_year, iso_week) -> list of holiday
    descriptions falling in that week. If multiple holidays land in the
    same week (rare), they're grouped together.

    Does NOT compute a capacity_multiplier itself -- that's a policy
    decision left to the caller (e.g. "one holiday in a 5-day week ->
    multiplier 0.8"), since different teams might reasonably choose
    different working-days-per-week assumptions.
    """
    holidays = get_mexican_holidays(year)
    impact = {}

    for holiday_date, description in holidays:
        iso_year, iso_week, _ = holiday_date.isocalendar()
        key = (iso_year, iso_week)
        impact.setdefault(key, []).append(description)

    return impact
