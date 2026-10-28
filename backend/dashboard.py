"""
Everything the manager dashboard shows, computed in one place and returned by a
single request (GET /dashboard), so the page is fast and the numbers cannot
drift from the other views:

  * lateness comes from lateness.classify_lateness, like /orders
  * occupancy uses the same arithmetic as /teams/{id}/occupancy (the Ocupación tab):
    tons allocated in the ISO weeks the month touches / capacity of those weeks
  * material totals come from calculations.monthly_requirements (the Requerimientos tab)
"""

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from calculations import monthly_requirements
from lateness import classify_lateness

ATTENTION_LIMIT = 5      # how many late orders the dashboard lists


def _previous(year: int, month: int):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _iso_weeks_touching(year: int, month: int):
    """Every ISO (year, week) the calendar month touches, day by day."""
    weeks = set()
    day = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    while day <= last:
        iso = day.isocalendar()
        weeks.add((iso[0], iso[1]))
        day += timedelta(days=1)
    return sorted(weeks)


def _order_stats(orders):
    """Counts for a batch of orders. 'Evaluated' = planned AND has a requested date to compare against."""
    counts = {"on_time": 0, "warning": 0, "critical": 0}
    scheduled = 0
    for order in orders:
        if order.calculated_delivery_date is not None:
            scheduled += 1
        _, status, _ = classify_lateness(order.calculated_delivery_date, order.requested_delivery_date)
        if status:
            counts[status] += 1
    evaluated = sum(counts.values())
    return {
        "orders": len(orders),
        "scheduled": scheduled,
        "unplanned": len(orders) - scheduled,
        **counts,
        "evaluated": evaluated,
        "on_time_pct": round(counts["on_time"] / evaluated * 100, 1) if evaluated else None,
        "tons": round(sum(float(o.quantity_requested) for o in orders), 2),
    }


class _Occupancy:
    """Occupancy of every team in every month of a year, from two queries."""

    def __init__(self, year: int, db: Session):
        self.year = year
        self.teams = db.query(models.Team).order_by(models.Team.sequence_order).all()

        self.allocated = defaultdict(float)
        rows = (
            db.query(models.CapacityAllocation.team_id, models.CapacityAllocation.year,
                     models.CapacityAllocation.week_number, func.sum(models.CapacityAllocation.quantity_allocated))
            .group_by(models.CapacityAllocation.team_id, models.CapacityAllocation.year,
                      models.CapacityAllocation.week_number)
            .all()
        )
        for team_id, iso_year, week, total in rows:
            self.allocated[(team_id, iso_year, week)] = float(total or 0)

        self.multiplier = {
            (e.team_id, e.year, e.week_number): float(e.capacity_multiplier)
            for e in db.query(models.TeamWeekException).all()
        }

    def team_month(self, team, month: int):
        total_allocated = total_capacity = 0.0
        peak = None
        for iso_year, week in _iso_weeks_touching(self.year, month):
            capacity = team.weekly_capacity * self.multiplier.get((team.id, iso_year, week), 1.0)
            allocated = self.allocated.get((team.id, iso_year, week), 0.0)
            total_allocated += allocated
            total_capacity += capacity
            if allocated > 0 and capacity > 0:
                pct = round(allocated / capacity * 100, 1)
                if peak is None or pct > peak["pct"]:
                    peak = {"week": week, "year": iso_year, "pct": pct}
        return {
            "team_id": team.id,
            "team_name": team.name,
            "sequence_order": team.sequence_order,
            "occupancy_pct": round(total_allocated / total_capacity * 100, 1) if total_capacity > 0 else None,
            "allocated": round(total_allocated, 2),
            "capacity": round(total_capacity, 2),
            "peak_week": peak,
        }

    def plant_month(self, month: int):
        """Plant average (mean of the teams) and the tons allocated in that month's weeks."""
        rows = [self.team_month(team, month) for team in self.teams]
        pcts = [r["occupancy_pct"] for r in rows if r["occupancy_pct"] is not None]
        return {
            "teams": rows,
            "pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
            "allocated": round(sum(r["allocated"] for r in rows), 2),
        }


def default_period(db: Session):
    """The month the dashboard opens on: the latest planned month, else the latest month with orders, else today's."""
    planned = db.query(models.MonthPlan).order_by(
        models.MonthPlan.planning_year.desc(), models.MonthPlan.planning_month.desc()).first()
    if planned:
        return planned.planning_year, planned.planning_month
    latest = db.query(models.Order.planning_year, models.Order.planning_month).order_by(
        models.Order.planning_year.desc(), models.Order.planning_month.desc()).first()
    if latest:
        return latest[0], latest[1]
    today = date.today()
    return today.year, today.month


def dashboard_summary(year, month, db: Session):
    if year is None or month is None:
        year, month = default_period(db)
    prev_year, prev_month = _previous(year, month)

    # --- orders: one query covers the year (and last December, for January's comparison)
    years = {year, prev_year}
    by_period = defaultdict(list)
    for order in db.query(models.Order).filter(models.Order.planning_year.in_(years)).all():
        by_period[(order.planning_year, order.planning_month)].append(order)

    planned_months = {(m.planning_year, m.planning_month) for m in db.query(models.MonthPlan).all()}
    occupancy = {year: _Occupancy(year, db)}
    if prev_year != year:
        occupancy[prev_year] = _Occupancy(prev_year, db)

    # --- the twelve-month series behind the charts
    months = []
    for m in range(1, 13):
        stats = _order_stats(by_period[(year, m)])
        plant = occupancy[year].plant_month(m)
        months.append({
            "month": m,
            **{k: stats[k] for k in ("orders", "scheduled", "unplanned", "on_time", "warning", "critical", "on_time_pct", "tons")},
            "planned": (year, m) in planned_months,
            # a month nothing is allocated in is a gap in the line, not a 0% dip
            "occupancy_pct": plant["pct"] if plant["allocated"] > 0 else None,
        })

    # --- the selected month and the one before it
    current = _order_stats(by_period[(year, month)])
    previous = _order_stats(by_period[(prev_year, prev_month)])
    plant_now = occupancy[year].plant_month(month)
    plant_before = occupancy[prev_year].plant_month(prev_month)

    team_rows = plant_now["teams"]
    loaded = [t for t in team_rows if t["occupancy_pct"] is not None and t["allocated"] > 0]
    busiest = max(loaded, key=lambda t: t["occupancy_pct"]) if loaded else None

    totals = monthly_requirements(year, month, db)["totals"]

    late = []
    for order in by_period[(year, month)]:
        days_late, status, _ = classify_lateness(order.calculated_delivery_date, order.requested_delivery_date)
        if status in ("warning", "critical"):
            late.append({
                "order_id": order.id,
                "customer_name": order.customer_name,
                "days_late": days_late,
                "lateness_status": status,
                "quantity_requested": float(order.quantity_requested),
                "requested_delivery_date": str(order.requested_delivery_date),
                "calculated_delivery_date": str(order.calculated_delivery_date),
            })
    late.sort(key=lambda o: (-o["days_late"], o["order_id"]))

    return {
        "year": year,
        "month": month,
        "previous": {"year": prev_year, "month": prev_month},
        "is_planned": (year, month) in planned_months,
        "kpis": {
            "orders": {"total": current["orders"], "scheduled": current["scheduled"],
                       "unplanned": current["unplanned"], "previous_total": previous["orders"]},
            "on_time": {"pct": current["on_time_pct"], "on_time": current["on_time"],
                        "warning": current["warning"], "critical": current["critical"],
                        "evaluated": current["evaluated"], "previous_pct": previous["on_time_pct"]},
            "occupancy": {"pct": plant_now["pct"], "previous_pct": plant_before["pct"]},
            "bottleneck": {"team_name": busiest["team_name"], "pct": busiest["occupancy_pct"]} if busiest else None,
            "tons": {"ordered": current["tons"], "previous_ordered": previous["tons"],
                     "raw": totals["raw"], "overall_yield": totals["overall_yield"]},
        },
        "months": months,
        "teams": team_rows,
        "attention": {"total": len(late), "orders": late[:ATTENTION_LIMIT]},
    }
