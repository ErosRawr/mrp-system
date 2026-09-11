"""
Shared logic for determining whether a team works on a given calendar date.

Precedence, highest to lowest:
    1. TeamScheduleException for that exact date (holiday, maintenance,
       rush shift, etc.) -- always wins, in either direction.
    2. TeamWeeklySchedule for that weekday (the recurring pattern).
    3. If neither exists, default to "working" (permissive), and flag it
       so callers can surface that the answer is a guess, not real data.
"""

from sqlalchemy.orm import Session
import models


def build_team_calendar(team_id: int, db: Session):
    """
    Pre-loads a team's weekly pattern and date exceptions once, returning
    a small object with an `is_working(date)` method. Building this once
    per team (rather than querying inside a day-by-day loop) keeps the
    scheduling loops from hammering the database on every iteration.
    """
    weekly_rows = (
        db.query(models.TeamWeeklySchedule)
        .filter(models.TeamWeeklySchedule.team_id == team_id)
        .all()
    )
    weekly_map = {row.day_of_week: row.is_working_day for row in weekly_rows}

    exception_rows = (
        db.query(models.TeamScheduleException)
        .filter(models.TeamScheduleException.team_id == team_id)
        .all()
    )
    exception_map = {row.date: row.is_working_day for row in exception_rows}

    class TeamCalendar:
        def is_working(self, on_date):
            """
            Returns (is_working: bool, used_default: bool).
            used_default is True only when neither an exception nor a
            weekly pattern entry exists for this date, meaning the
            answer is a permissive guess rather than real schedule data.
            """
            if on_date in exception_map:
                return exception_map[on_date], False

            weekday = on_date.weekday()
            if weekday in weekly_map:
                return weekly_map[weekday], False

            return True, True  # no data at all -- assume working, flag it

    return TeamCalendar()