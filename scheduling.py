"""
Capacity-aware scheduling.

This is separate from calculations.py (which computes gross/net MATERIAL
requirements per team) — this module answers a different question:
given everything else already scheduled, WHEN does a specific team actually
have room to process this order's quantity?

FIFO is enforced structurally: orders should be scheduled in order_date
order, and each order's allocations become visible to every order scheduled
after it. Nothing here re-orders or re-shuffles existing allocations —
once an order is scheduled, its claim on capacity is fixed.
"""

import math
from datetime import timedelta
from sqlalchemy.orm import Session
import models
from team_calendar import build_team_calendar


def _already_allocated(team_id: int, on_date, db: Session) -> float:
    """Sum of capacity already claimed by OTHER orders on this team/date."""
    rows = (
        db.query(models.CapacityAllocation)
        .filter(
            models.CapacityAllocation.team_id == team_id,
            models.CapacityAllocation.date == on_date,
        )
        .all()
    )
    return sum(float(r.quantity_allocated) for r in rows)


def schedule_team_capacity(team_id: int, order_id: int, quantity_needed: float,
                            start_date, db: Session, commit: bool = True):
    """
    Walks forward from start_date, consuming whatever capacity is left
    on each working day (after subtracting what's already allocated to
    other orders), until quantity_needed is fully covered.

    Returns a dict describing the schedule outcome:
        {
            "start_date": ...,
            "end_date": ...,
            "calendar_days_elapsed": ...,
            "daily_breakdown": [ {date, allocated, remaining_capacity_before}, ... ],
            "schedule_data_incomplete": bool  # true if any day had no weekly pattern set
        }

    If commit=True, writes CapacityAllocation rows for this order so future
    scheduling calls see this order's claim. If commit=False, this is a
    dry-run (useful for previewing without locking in capacity).
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        return None

    daily_capacity = float(team.daily_capacity)
    calendar = build_team_calendar(team_id, db)

    remaining_needed = quantity_needed
    current_date = start_date
    daily_breakdown = []
    used_default = False
    calendar_days_elapsed = 0
    max_iterations = 3650  # ~10 years safety cap, avoids infinite loop on bad data

    while remaining_needed > 0 and calendar_days_elapsed < max_iterations:
        is_working, was_default = calendar.is_working(current_date)
        if was_default:
            used_default = True

        if is_working and daily_capacity > 0:
            already_used = _already_allocated(team_id, current_date, db)
            free_capacity = max(daily_capacity - already_used, 0.0)

            if free_capacity > 0:
                allocate_today = min(free_capacity, remaining_needed)
                daily_breakdown.append({
                    "date": str(current_date),
                    "allocated": round(allocate_today, 2),
                    "free_capacity_before": round(free_capacity, 2),
                })

                if commit and allocate_today > 0:
                    db.add(models.CapacityAllocation(
                        team_id=team_id,
                        order_id=order_id,
                        date=current_date,
                        quantity_allocated=allocate_today,
                    ))

                remaining_needed -= allocate_today

        if remaining_needed > 0:
            current_date = current_date + timedelta(days=1)
            calendar_days_elapsed += 1

    if commit:
        db.commit()

    return {
        "start_date": str(start_date),
        "end_date": str(current_date),
        "calendar_days_elapsed": calendar_days_elapsed + 1,
        "daily_breakdown": daily_breakdown,
        "schedule_data_incomplete": used_default,
        "fully_scheduled": remaining_needed <= 0,
    }