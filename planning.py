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

Weekly capacity honors TeamWeekException rows (holidays, maintenance):
a week's usable capacity is weekly_capacity * capacity_multiplier.
"""

import math
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models
from calculations import calculate_material_requirements
from heuristics import sort_orders_by_criterion
from capacity import get_effective_weekly_capacity


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


def _schedule_team_weekly(team_id: int, order_id: int, quantity_needed: float,
                           start_year: int, start_week: int, db: Session):
    """
    Walks forward week by week from (start_year, start_week), consuming
    whatever weekly capacity is left (after applying that week's
    exception multiplier and subtracting what other orders already
    claimed for that team/week), until quantity_needed is covered.

    Returns dict: {end_year, end_week, weeks_elapsed, breakdown, fully_scheduled}
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        return None

    # Guard against a misconfigured team. A multiplier of 0 on a single
    # week is NOT an error -- that week is simply skipped in the loop.
    if team.weekly_capacity <= 0:
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
        effective_capacity = get_effective_weekly_capacity(team, year, week, db)
        already_used = _already_allocated_this_week(team_id, year, week, db)
        free_capacity = max(effective_capacity - already_used, 0.0)

        if free_capacity > 0:
            allocate_this_week = min(free_capacity, remaining_needed)
            breakdown.append({
                "year": year,
                "week_number": week,
                "allocated": round(allocate_this_week, 2),
                "free_capacity_before": round(free_capacity, 2),
                "effective_capacity": round(effective_capacity, 2),
            })

            db.add(models.CapacityAllocation(
                team_id=team_id,
                order_id=order_id,
                year=year,
                week_number=week,
                quantity_allocated=allocate_this_week,
            ))
            db.flush()  # make this allocation visible to subsequent queries
                        # in the same session, BEFORE the final commit --
                        # otherwise later orders in this same planning run
                        # won't see earlier orders' claims and can over-allocate.

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


def _plan_orders_in_sequence(orders, db: Session):
    """
    Core scheduling loop: given orders ALREADY SORTED in the desired
    processing order, walks each one through its full team chain,
    consuming weekly capacity as it goes. Writes calculated_delivery_date
    onto each Order object and CapacityAllocation rows via db.add(), but
    does NOT commit -- the caller decides whether to commit or roll back.

    This is shared by both the real planning run (which commits) and the
    comparison runner (which rolls back after collecting results), so the
    actual scheduling logic only exists in one place.
    """
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

        steps_in_production_order = list(reversed(requirements["steps"]))

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

        final_step = team_schedule_results[-1]
        calculated_delivery_date = _week_end_date(final_step["end_year"], final_step["end_week"])

        order.calculated_delivery_date = calculated_delivery_date
        db.add(order)

        is_late = None
        lateness_status = None
        days_late = None
        if order.requested_delivery_date:
            days_late = (calculated_delivery_date - order.requested_delivery_date).days
            is_late = days_late > 7
            if days_late <= 7:
                lateness_status = "on_time"
            elif days_late <= 14:
                lateness_status = "warning"
            else:
                lateness_status = "critical"

        results.append({
            "order_id": order.id,
            "customer_name": order.customer_name,
            "quantity_requested": float(order.quantity_requested),
            "is_priority": order.is_priority,
            "tipo_pedido": order.tipo_pedido,
            "requested_delivery_date": str(order.requested_delivery_date) if order.requested_delivery_date else None,
            "calculated_delivery_date": str(calculated_delivery_date),
            "is_late": is_late,
            "days_late": days_late,
            "lateness_status": lateness_status,
            "team_schedule": team_schedule_results,
        })

    return results


def run_monthly_planning(planning_year: int, planning_month: int, db: Session, criterion: str = "peps"):
    """
    The core spec requirement: takes every order registered for
    (planning_year, planning_month), sorts according to `criterion`, and
    computes a calculated_delivery_date for each -- walking the full team
    chain in production order (upstream first), consuming weekly capacity
    as it goes so orders queue realistically against each other.

    criterion selects the sort order orders are PROCESSED in (see
    heuristics.py): "peps" (pure FIFO by requested date, the default),
    "prioritario" (priority orders first), or "heuristica" (priority,
    then tonnage at/above 15k tons, then tipo_pedido rank).

    Writes calculated_delivery_date back onto each Order, and commits
    CapacityAllocation rows so the run's effects are persisted, not just
    returned.

    Idempotent: re-running for the same month first clears any
    CapacityAllocation rows previously committed by an earlier run for
    that month's orders, so re-running produces a clean result rather
    than stacking duplicate allocations on top of the old ones.
    """
    orders = (
        db.query(models.Order)
        .filter(
            models.Order.planning_year == planning_year,
            models.Order.planning_month == planning_month,
        )
        .all()
    )

    order_ids = [o.id for o in orders]
    if order_ids:
        db.query(models.CapacityAllocation).filter(
            models.CapacityAllocation.order_id.in_(order_ids)
        ).delete(synchronize_session=False)
        db.flush()

    orders = sort_orders_by_criterion(orders, criterion)
    results = _plan_orders_in_sequence(orders, db)

    db.commit()

    return {
        "planning_year": planning_year,
        "planning_month": planning_month,
        "criterion": criterion,
        "orders_planned": len(results),
        "results": results,
    }


def compare_planning_criteria(planning_year: int, planning_month: int, db: Session,
                               criteria: list = None):
    """
    Runs planning under multiple criteria WITHOUT committing any of them --
    lets you compare how different prioritization strategies would play
    out before choosing one to actually run for real (via
    run_monthly_planning, which does commit).

    Each criterion is evaluated against a clean slate: prior
    CapacityAllocation rows for that month's orders are cleared (within
    the uncommitted transaction) before each criterion runs, so criteria
    don't bleed into each other's results. The whole comparison is rolled
    back at the end -- nothing is persisted by this function.
    """
    if criteria is None:
        criteria = ["peps", "prioritario", "heuristica"]

    orders = (
        db.query(models.Order)
        .filter(
            models.Order.planning_year == planning_year,
            models.Order.planning_month == planning_month,
        )
        .all()
    )
    order_ids = [o.id for o in orders]

    comparison = {}

    try:
        for criterion in criteria:
            if order_ids:
                db.query(models.CapacityAllocation).filter(
                    models.CapacityAllocation.order_id.in_(order_ids)
                ).delete(synchronize_session=False)
                db.flush()

            sorted_orders = sort_orders_by_criterion(orders, criterion)
            results = _plan_orders_in_sequence(sorted_orders, db)

            on_time = sum(1 for r in results if r.get("lateness_status") == "on_time")
            warning = sum(1 for r in results if r.get("lateness_status") == "warning")
            critical = sum(1 for r in results if r.get("lateness_status") == "critical")

            comparison[criterion] = {
                "results": results,
                "summary": {
                    "on_time": on_time,
                    "warning": warning,
                    "critical": critical,
                    "errors": sum(1 for r in results if "error" in r),
                },
            }
    finally:
        # Always roll back -- this function never persists anything,
        # regardless of how it exits.
        db.rollback()

    return {
        "planning_year": planning_year,
        "planning_month": planning_month,
        "criteria_compared": criteria,
        "comparison": comparison,
    }