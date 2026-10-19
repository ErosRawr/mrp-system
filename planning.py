"""
Monthly planning run.

Per spec: before a new month starts, a planning process takes ALL orders
registered for that month, sorts them by requested delivery date, and
calculates a delivery date (expressed as a week) for each one -- walking
each order through the full team chain and consuming each team's weekly
capacity bucket as it goes, so later orders see less capacity remaining
if earlier orders (with earlier requested dates) already claimed it.

CapacityAllocation rows act as a ledger of what has been claimed, so the
calculation for order N naturally accounts for orders 1..N-1 processed
before it in the same run.
"""

from datetime import date, timedelta
from sqlalchemy.orm import Session
import models
from calculations import calculate_material_requirements
from heuristics import sort_orders_by_criterion
from lateness import classify_lateness


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


def _capacity_multiplier(team_id: int, year: int, week_number: int, db: Session) -> float:
    """
    Returns the capacity multiplier for a team/week from TeamWeekException.
    1.0 (full capacity) when no exception exists, 0.0 means fully unavailable.
    """
    exc = (
        db.query(models.TeamWeekException)
        .filter(
            models.TeamWeekException.team_id == team_id,
            models.TeamWeekException.year == year,
            models.TeamWeekException.week_number == week_number,
        )
        .first()
    )
    return float(exc.capacity_multiplier) if exc else 1.0


def _schedule_team_weekly(team_id: int, order_id: int, quantity_needed: float,
                           start_year: int, start_week: int, db: Session):
    """
    Walks forward week by week from (start_year, start_week), consuming
    whatever weekly capacity is left (after subtracting what other orders
    already claimed for that team/week), until quantity_needed is covered.

    Returns dict: {end_year, end_week, weeks_elapsed, breakdown, fully_scheduled}
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        return None

    weekly_capacity = team.weekly_capacity
    if weekly_capacity <= 0:
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
        multiplier = _capacity_multiplier(team_id, year, week, db)
        effective_capacity = weekly_capacity * multiplier
        already_used = _already_allocated_this_week(team_id, year, week, db)
        free_capacity = max(effective_capacity - already_used, 0.0)

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

        days_late, lateness_status, is_late = classify_lateness(
            calculated_delivery_date, order.requested_delivery_date
        )

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


def _month_key_after(query, year: int, month: int, inclusive: bool):
    """Filters a MonthPlan query to months at/after (year, month), in calendar order."""
    cmp_month = (models.MonthPlan.planning_month >= month) if inclusive else (models.MonthPlan.planning_month > month)
    return (
        query.filter((models.MonthPlan.planning_year > year) |
                     ((models.MonthPlan.planning_year == year) & cmp_month))
        .order_by(models.MonthPlan.planning_year, models.MonthPlan.planning_month)
    )


def _orders_of_month(year: int, month: int, db: Session):
    return (
        db.query(models.Order)
        .filter(models.Order.planning_year == year, models.Order.planning_month == month)
        .all()
    )


def _orders_from_month(year: int, month: int, db: Session):
    """Every order planned for (year, month) OR any later month."""
    return (
        db.query(models.Order)
        .filter((models.Order.planning_year > year) |
                ((models.Order.planning_year == year) & (models.Order.planning_month >= month)))
        .all()
    )


def _clear_allocations(order_ids, db: Session):
    if order_ids:
        db.query(models.CapacityAllocation).filter(
            models.CapacityAllocation.order_id.in_(order_ids)
        ).delete(synchronize_session=False)
        db.flush()


def _plan_month(year: int, month: int, criterion: str, db: Session):
    """Plans ONE month's orders into whatever capacity is currently free.
    Does not clear anything and does not commit."""
    orders = sort_orders_by_criterion(_orders_of_month(year, month, db), criterion)
    return _plan_orders_in_sequence(orders, db)


def _replan_months(month_plans, db: Session):
    """
    Clears and re-plans the given MonthPlan rows IN CALENDAR ORDER, each with
    its own saved criterion. Because earlier months are planned first, they
    always get first claim on capacity. Does not commit.
    """
    for mp in month_plans:
        _clear_allocations([o.id for o in _orders_of_month(mp.planning_year, mp.planning_month, db)], db)

    summaries = []
    for mp in month_plans:
        results = _plan_month(mp.planning_year, mp.planning_month, mp.criterion, db)
        summaries.append({
            "planning_year": mp.planning_year,
            "planning_month": mp.planning_month,
            "criterion": mp.criterion,
            "orders_planned": len(results),
            "results": results,
        })
    return summaries


def run_monthly_planning(planning_year: int, planning_month: int, db: Session, criterion: str = "peps"):
    """
    Plans (planning_year, planning_month) with `criterion`.

    Months are processed in calendar order: earlier months get first claim on
    capacity. So after this month is planned, every LATER month that was
    already planned is re-planned too (each with its own saved criterion),
    otherwise its allocations would be stale -- computed before this month
    existed, or against a different version of it.

    Returns this month's results plus `replanned_months`, a short summary of
    the later months that were re-planned.

    Idempotent: re-running clears this month's (and later planned months')
    allocations first, so nothing stacks on top of old allocations.
    """
    mp = (
        db.query(models.MonthPlan)
        .filter(models.MonthPlan.planning_year == planning_year,
                models.MonthPlan.planning_month == planning_month)
        .first()
    )
    if mp is None:
        mp = models.MonthPlan(planning_year=planning_year, planning_month=planning_month, criterion=criterion)
        db.add(mp)
    else:
        mp.criterion = criterion
    db.flush()

    month_plans = _month_key_after(db.query(models.MonthPlan), planning_year, planning_month, inclusive=True).all()
    summaries = _replan_months(month_plans, db)
    db.commit()

    this_month = summaries[0]
    return {
        "planning_year": planning_year,
        "planning_month": planning_month,
        "criterion": criterion,
        "orders_planned": this_month["orders_planned"],
        "results": this_month["results"],
        "replanned_months": [
            {k: s[k] for k in ("planning_year", "planning_month", "criterion", "orders_planned")}
            for s in summaries[1:]
        ],
    }


def replan_all(db: Session):
    """
    Re-plans every planned month from the earliest one, in order, with each
    month's saved criterion. Use after anything that changes capacity or
    availability (week exceptions, holidays, disruptions, team edits).
    """
    month_plans = (
        db.query(models.MonthPlan)
        .order_by(models.MonthPlan.planning_year, models.MonthPlan.planning_month)
        .all()
    )
    summaries = _replan_months(month_plans, db)
    db.commit()
    return {
        "months_replanned": [
            {k: s[k] for k in ("planning_year", "planning_month", "criterion", "orders_planned")}
            for s in summaries
        ]
    }


def compare_planning_criteria(planning_year: int, planning_month: int, db: Session,
                               criteria: list = None):
    """
    Runs planning under multiple criteria WITHOUT committing any of them --
    lets you compare how different prioritization strategies would play
    out before choosing one to actually run for real (via
    run_monthly_planning, which does commit).

    The comparison sees only the capacity left by EARLIER months, exactly as
    the real run will: this month's allocations AND those of every later
    month are cleared (inside the uncommitted transaction) before each
    criterion runs. Later months therefore cannot distort the result, and
    criteria do not bleed into each other. Everything is rolled back at the
    end -- nothing is persisted by this function.

    `later_planned_months` lists the months that WOULD be re-planned if you
    commit one of these criteria.
    """
    if criteria is None:
        criteria = ["peps", "prioritario", "heuristica"]

    later_planned = [
        {"planning_year": mp.planning_year, "planning_month": mp.planning_month, "criterion": mp.criterion}
        for mp in _month_key_after(db.query(models.MonthPlan), planning_year, planning_month, inclusive=False).all()
    ]
    affected_ids = [o.id for o in _orders_from_month(planning_year, planning_month, db)]

    comparison = {}

    try:
        for criterion in criteria:
            _clear_allocations(affected_ids, db)
            results = _plan_month(planning_year, planning_month, criterion, db)

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
        "later_planned_months": later_planned,
        "comparison": comparison,
    }
