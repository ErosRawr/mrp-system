"""
Single source of truth for a team's capacity in a given ISO week.

Both the planner (planning.py) and the occupancy report (main.py) use
these helpers, so they can never disagree about how much capacity a team
actually has in a week with a holiday or maintenance exception.
"""

from sqlalchemy import func
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


OVERLOAD_TOLERANCE_TONS = 0.01   # rounding noise is not an overload


def availability_overloads(db: Session, year: int = None):
    """
    Team-weeks where the saved plan holds MORE work than the team's availability
    allows. A fresh plan never does (the planner respects every exception), so one
    appearing means availability changed after planning and the plan is stale: run
    the planning again. Same rule the tests use to check the capacity ledger.
    """
    teams = {t.id: t for t in db.query(models.Team).all()}
    multiplier = {
        (e.team_id, e.year, e.week_number): float(e.capacity_multiplier)
        for e in db.query(models.TeamWeekException).all()
    }
    query = (
        db.query(models.CapacityAllocation.team_id, models.CapacityAllocation.year,
                 models.CapacityAllocation.week_number, func.sum(models.CapacityAllocation.quantity_allocated))
        .group_by(models.CapacityAllocation.team_id, models.CapacityAllocation.year,
                  models.CapacityAllocation.week_number)
    )
    if year is not None:
        query = query.filter(models.CapacityAllocation.year == year)

    rows = []
    for team_id, iso_year, week, total in query.all():
        team = teams.get(team_id)
        if team is None:
            continue
        allocated = float(total or 0)
        capacity = team.weekly_capacity * multiplier.get((team_id, iso_year, week), 1.0)
        if allocated > capacity + OVERLOAD_TOLERANCE_TONS:
            rows.append({
                "team_id": team_id,
                "team_name": team.name,
                "sequence_order": team.sequence_order,
                "year": iso_year,
                "week_number": week,
                "allocated": round(allocated, 2),
                "capacity": round(capacity, 2),
                "excess": round(allocated - capacity, 2),
            })
    rows.sort(key=lambda r: (r["year"], r["week_number"], r["sequence_order"]))
    return rows
