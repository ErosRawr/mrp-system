"""
Manual planning: the planner picks the order sequence by hand (Expedite and
Estandar blocks, flattened into one list) and can park orders in Hold.

Two operations, mirroring compare/run for the automatic criteria:

  preview_manual  plans the given sequence inside a transaction and ROLLS
                  BACK. Nothing is stored; the answer is exactly what a save
                  would produce.
  save_manual     stores the sequence (ManualSlot rows), marks the month as
                  planned with criterion "manual", and re-plans it plus every
                  later planned month, same as run_monthly_planning does.

The stored sequence is what lets a later replan (an earlier month changed, an
availability change, replan-all) rebuild this month exactly as it was hand-made.
"""

from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
from capacity import get_effective_weekly_capacity
from planning import (
    _already_allocated_this_week,
    _clear_allocations,
    _month_key_after,
    _orders_from_month,
    _orders_of_month,
    _plan_orders_in_sequence,
    run_monthly_planning,
)
from validation import bad, require_month, require_year


class ManualPlanRequest(BaseModel):
    year: int
    month: int
    order_ids: list[int]          # planned, in this order (Expedite first, then Estandar)
    hold_ids: list[int] = []      # excluded from the plan


def _validated_orders(req: ManualPlanRequest, db: Session):
    """
    The request must describe the month exactly: every order of the month
    appears once, either in order_ids or in hold_ids, and nothing else does.
    Strict on purpose: what the planner sees on screen is what gets planned.
    """
    require_year(req.year)
    require_month(req.month)

    month_orders = {o.id: o for o in _orders_of_month(req.year, req.month, db)}
    if not month_orders:
        bad(f"There are no orders for {req.year}-{req.month:02d}, so there is nothing to plan")

    ids = req.order_ids + req.hold_ids
    if len(ids) != len(set(ids)):
        bad("An order appears more than once (or in both the plan and Hold)")

    unknown = sorted(set(ids) - set(month_orders))
    if unknown:
        bad(f"Orders {unknown} do not belong to {req.year}-{req.month:02d}")

    missing = sorted(set(month_orders) - set(ids))
    if missing:
        bad(f"Orders {missing} are not placed in any block -- reload the month and try again")

    return month_orders


def _summarize(results):
    def count(status):
        return sum(1 for r in results if r.get("lateness_status") == status)

    return {
        "on_time": count("on_time"),
        "warning": count("warning"),
        "critical": count("critical"),
        "errors": sum(1 for r in results if "error" in r),
    }


def _bottleneck(results, db: Session):
    """
    Name of the team whose busiest week (among the weeks this plan uses) is the
    most loaded, counting everything already allocated that week. Must run
    before the preview's rollback, while the plan's allocations still exist.
    """
    planned_ids = [r["order_id"] for r in results if "error" not in r]
    if not planned_ids:
        return None

    cells = (
        db.query(models.CapacityAllocation.team_id,
                 models.CapacityAllocation.year,
                 models.CapacityAllocation.week_number)
        .filter(models.CapacityAllocation.order_id.in_(planned_ids))
        .distinct()
        .all()
    )
    teams = {t.id: t for t in db.query(models.Team).all()}

    # Several team-weeks can be completely full at once. Ties go to the team
    # with the smaller weekly capacity (the structurally scarcer one), so the
    # answer never depends on the order the database returns rows in.
    worst_key, worst_name = None, None
    for team_id, year, week in cells:
        team = teams[team_id]
        capacity = get_effective_weekly_capacity(team, year, week, db)
        if capacity <= 0:
            continue
        ratio = _already_allocated_this_week(team_id, year, week, db) / capacity
        key = (round(ratio, 6), -team.weekly_capacity)
        if worst_key is None or key > worst_key:
            worst_key, worst_name = key, team.name
    return worst_name


def preview_manual(req: ManualPlanRequest, db: Session):
    month_orders = _validated_orders(req, db)
    to_plan = [month_orders[i] for i in req.order_ids]

    later_planned = [
        {"planning_year": mp.planning_year, "planning_month": mp.planning_month, "criterion": mp.criterion}
        for mp in _month_key_after(db.query(models.MonthPlan), req.year, req.month, inclusive=False).all()
    ]
    # Like compare: see only the capacity left by EARLIER months.
    affected_ids = [o.id for o in _orders_from_month(req.year, req.month, db)]

    try:
        _clear_allocations(affected_ids, db)
        results = _plan_orders_in_sequence(to_plan, db)
        summary = _summarize(results)
        summary["bottleneck"] = _bottleneck(results, db)
    finally:
        db.rollback()   # a preview never persists, however it exits

    return {
        "planning_year": req.year,
        "planning_month": req.month,
        "criterion": "manual",
        "results": results,
        "summary": summary,
        "held_order_ids": req.hold_ids,
        "later_planned_months": later_planned,
    }


def save_manual(req: ManualPlanRequest, db: Session):
    _validated_orders(req, db)
    ids = req.order_ids + req.hold_ids

    # Replace this month's sequence. Also drop any slot these orders still have
    # from another month (an order whose planning month was edited).
    db.query(models.ManualSlot).filter(
        or_(
            and_(models.ManualSlot.planning_year == req.year,
                 models.ManualSlot.planning_month == req.month),
            models.ManualSlot.order_id.in_(ids),
        )
    ).delete(synchronize_session=False)

    for position, order_id in enumerate(req.order_ids):
        db.add(models.ManualSlot(planning_year=req.year, planning_month=req.month,
                                 order_id=order_id, position=position, is_held=False))
    for position, order_id in enumerate(req.hold_ids):
        db.add(models.ManualSlot(planning_year=req.year, planning_month=req.month,
                                 order_id=order_id, position=position, is_held=True))
    db.flush()

    result = run_monthly_planning(req.year, req.month, db, criterion="manual")
    result["held_order_ids"] = req.hold_ids
    return result


def manual_sequence(year: int, month: int, db: Session):
    """
    The saved hand-made sequence for a month, so the planner can see it again
    after a reload. Both lists are in saved order; they are empty when the month
    was never planned by hand (or an automatic criterion replaced the sequence).
    """
    require_year(year)
    require_month(month)
    slots = (
        db.query(models.ManualSlot)
        .filter(models.ManualSlot.planning_year == year,
                models.ManualSlot.planning_month == month)
        .order_by(models.ManualSlot.is_held, models.ManualSlot.position)
        .all()
    )
    return {
        "planning_year": year,
        "planning_month": month,
        "order_ids": [s.order_id for s in slots if not s.is_held],
        "hold_ids": [s.order_id for s in slots if s.is_held],
    }
