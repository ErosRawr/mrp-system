"""
Single source of truth for a team's capacity in a given ISO week.

Both the planner (planning.py) and the occupancy report (main.py) use
these helpers, so they can never disagree about how much capacity a team
actually has in a week with a holiday or maintenance exception.
"""

from sqlalchemy.orm import Session
import models


def get_week_exception(team_id: int, year: int, week_number: int, db: Session):
    """Returns the TeamWeekException for (team, year, week), or None."""
    return (
        db.query(models.TeamWeekException)
        .filter(
            models.TeamWeekException.team_id == team_id,
            models.TeamWeekException.year == year,
            models.TeamWeekException.week_number == week_number,
        )
        .first()
    )


def get_effective_weekly_capacity(team, year: int, week_number: int, db: Session) -> float:
    """
    Base weekly capacity scaled by that week's exception multiplier
    (1.0 when no exception exists, 0.0 when the week is fully off).
    """
    exc = get_week_exception(team.id, year, week_number, db)
    multiplier = float(exc.capacity_multiplier) if exc else 1.0
    return team.weekly_capacity * multiplier
