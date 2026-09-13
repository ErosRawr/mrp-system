"""
Monthly planning run.

Per spec: before a new month starts, a planning process takes ALL orders
registered for that month, sorts them by requested delivery date, and
calculates a delivery date (expressed as a week) for each one -- walking
each order through the full team chain and consuming each team's weekly
capacity bucket as it goes, so later orders see less capacity remaining
if earlier orders (with earlier requested dates) already claimed it.

This intentionally reuses the same "ledger" pattern already proven in the
day-level scheduler: CapacityAllocation rows record what's been claimed,
so the calculation for order N naturally accounts for orders 1..N-1
processed before it in the same run.
"""

import math
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models
from calculations import calculate_material_requirements


def _iso_year_week(d: date):
    """Returns (iso_year, iso_week_number) for a date."""
    iso = d.isocalendar()
    return iso[0], iso[1]


def _week_end_date(year: int, week_number: int):
    """
    Returns the Sunday (end of week) for a given ISO year/week -- used
    as the human-facing 'delivery date' representing that week, since the
    spec wants delivery expressed as a week, not an exact day.
    """
    jan4 = date(year, 1, 4)  # ISO week 1 always contains Jan 4th
    week1_monday = jan4 - timedelta(days=jan4.isoweekday() - 1)
    target_monday = week1_monday + timedelta(weeks=week_number - 1)
    return target_monday + timedelta(days=6)  # Sunday of that week


def _already_allocated_this_week(team_id: int, year: int, week_number: int, db: Session) -> float:
    rows = (
        db.query(models.CapacityAllocation)
        .filter(
            models.CapacityAllocation.team_id == team_id,
            models.CapacityAllocation.year == year,
            models.CapacityAllocation.week_number == week_number,
        )
        .all()
    )
    return sum(float(r.quantity_allocated) for r in rows)


def _get_capacity_multiplier(team_id: int, year: int, week_number: int, db: Session) -> float:
    """Returns the capacity_multiplier for this team/week, or 1.0 (full
    capacity) if no exception has been set."""
    exception = (
        db.query(models.TeamWeekException)
        .filter(
            models.TeamWeekException.team_id == team_id,
            models.TeamWeekException.year == year,
            models.TeamWeekException.week_number == week_number,
        )
        .first()
    )
    return float(exception.capacity_multiplier) if exception else 1.0


def _schedule_team_weekly(team_id: int, order_id: int, quantity_needed: float,
                           start_year: int, start_week: int, db: Session):
    """
    Walks forward week by week from (start_year, start_week), consuming
    whatever weekly capacity is left (after subtracting what other orders
    already claimed for that team/week, AND scaling down for any
    TeamWeekException such as a holiday or maintenance shutdown), until
    quantity_needed is covered.

    Returns dict: {end_year, end_week, weeks_elapsed, breakdown, fully_scheduled}
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        return None

    base_weekly_capacity = team.weekly_capacity
    if base_weekly_capacity <= 0:
        return {
            "end_year": start_year,
            "end_week": start_week,
            "weeks_elapsed": None,
            "breakdown": [],
            "fully_scheduled": False,
            "error": f"Team '{team.name}' has zero or invalid weekly capacity",
        }

    remaining_needed = quantity_needed
    year, week = start_year, start_week
    breakdown = []
    weeks_elapsed = 0
    max_iterations = 260  # ~5 years of weeks, safety cap

    while remaining_needed > 0 and weeks_elapsed < max_iterations:
        multiplier = _get_capacity_multiplier(team_id, year, week, db)
        effective_weekly_capacity = base_weekly_capacity * multiplier

        already_used = _already_allocated_this_week(team_id, year, week, db)
        free_capacity = max(effective_weekly_capacity - already_used, 0.0)

        if free_capacity > 0:
            allocate_this_week = min(free_capacity, remaining_needed)
            breakdown.append({
                "year": year,
                "week_number": week,
                "allocated": round(allocate_this_week, 2),
                "free_capacity_before": round(free_capacity, 2),
                "capacity_multiplier": multiplier,
            })

            db.add(models.CapacityAllocation(
                team_id=team_id,
                order_id=order_id,
                year=year,
                week_number=week,
                quantity_allocated=allocate_this_week,
            ))
            db.flush()

            remaining_needed -= allocate_this_week

        if remaining_needed > 0:
            week += 1
            if week > 52:
                week = 1
                year += 1
            weeks_elapsed += 1

    return {
        "end_year": year,
        "end_week": week,
        "weeks_elapsed": weeks_elapsed + 1,
        "breakdown": breakdown,
        "fully_scheduled": remaining_needed <= 0,
    }


def run_monthly_planning(planning_year: int, planning_month: int, db: Session):
    """
    The core spec requirement: takes every order registered for
    (planning_year, planning_month), sorts by requested_delivery_date,
    and computes a calculated_delivery_date for each -- walking the full
    team chain in production order (upstream first), consuming weekly
    capacity as it goes so orders queue realistically against each other.

    Writes calculated_delivery_date back onto each Order, and commits
    CapacityAllocation rows so the run's effects are persisted, not just
    returned.
    """
    orders = (
        db.query(models.Order)
        .filter(
            models.Order.planning_year == planning_year,
            models.Order.planning_month == planning_month,
        )
        .order_by(models.Order.requested_delivery_date.asc().nullslast())
        .all()
    )

    results = []

    for order in orders:
        requirements = calculate_material_requirements(order.id, db)
        if requirements is None or requirements.get("error"):
            results.append({
                "order_id": order.id,
                "customer_name": order.customer_name,
                "error": "Could not calculate material requirements for this order",
            })
            continue

        # requirements["steps"] is entry-team-first (downstream), upstream-last.
        # Production happens upstream-first, so reverse for time-chaining.
        steps_in_production_order = list(reversed(requirements["steps"]))

        # Start the chain at the order's registration week.
        start_year, start_week = _iso_year_week(order.order_date)
        next_year, next_week = start_year, start_week

        team_schedule_results = []
        scheduling_failed = False

        for step in steps_in_production_order:
            result = _schedule_team_weekly(
                team_id=step["team_id"],
                order_id=order.id,
                quantity_needed=step["output_needed"],
                start_year=next_year,
                start_week=next_week,
                db=db,
            )
            if result is None or result.get("error"):
                scheduling_failed = True
                team_schedule_results.append({
                    "team_name": step["team_name"],
                    **(result or {"error": "Team not found"}),
                })
                break

            team_schedule_results.append({
                "team_name": step["team_name"],
                **result,
            })

            # Next (downstream) team starts the week AFTER this team
            # finishes, since its output isn't ready until then.
            next_week = result["end_week"] + 1
            next_year = result["end_year"]
            if next_week > 52:
                next_week = 1
                next_year += 1

        if scheduling_failed:
            results.append({
                "order_id": order.id,
                "customer_name": order.customer_name,
                "error": "Scheduling failed -- see team_schedule for details",
                "team_schedule": team_schedule_results,
            })
            continue

        # The entry team (last in production order) finishing determines
        # the actual delivery date -- expressed as that week's end date.
        final_step = team_schedule_results[-1]
        calculated_delivery_date = _week_end_date(final_step["end_year"], final_step["end_week"])

        order.calculated_delivery_date = calculated_delivery_date
        db.add(order)

        is_late = None
        if order.requested_delivery_date:
            is_late = calculated_delivery_date > order.requested_delivery_date

        results.append({
            "order_id": order.id,
            "customer_name": order.customer_name,
            "quantity_requested": float(order.quantity_requested),
            "requested_delivery_date": str(order.requested_delivery_date) if order.requested_delivery_date else None,
            "calculated_delivery_date": str(calculated_delivery_date),
            "is_late": is_late,
            "team_schedule": team_schedule_results,
        })

    db.commit()

    return {
        "planning_year": planning_year,
        "planning_month": planning_month,
        "orders_planned": len(results),
        "results": results,
    }