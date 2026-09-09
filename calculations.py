import math
from datetime import timedelta
from sqlalchemy.orm import Session
import models


def _count_forward_working_days(team_id: int, start_date, days_needed: int, db: Session):
    """
    Starting from start_date, walks forward day by day until `days_needed`
    working days have been found for this team, using the team's recurring
    weekly pattern. If no weekly pattern is set for a given weekday, it's
    assumed to be a working day (permissive default, flagged in output).

    Returns (end_date, calendar_days_elapsed, used_default_for_any_day)
    """
    if days_needed <= 0:
        return start_date, 0, False

    weekly_rows = (
        db.query(models.TeamWeeklySchedule)
        .filter(models.TeamWeeklySchedule.team_id == team_id)
        .all()
    )
    weekly_map = {row.day_of_week: row.is_working_day for row in weekly_rows}

    working_days_found = 0
    calendar_days_elapsed = 0
    used_default = False
    current_date = start_date

    max_iterations = days_needed * 10 + 365

    while working_days_found < days_needed and calendar_days_elapsed < max_iterations:
        weekday = current_date.weekday()
        is_working = weekly_map.get(weekday)
        if is_working is None:
            is_working = True
            used_default = True

        if is_working:
            working_days_found += 1

        if working_days_found < days_needed:
            current_date = current_date + timedelta(days=1)
            calendar_days_elapsed += 1

    return current_date, calendar_days_elapsed + 1, used_default


def calculate_material_requirements(order_id: int, db: Session):
    """
    Walks backward from an order's entry team through team #1, computing
    how much material each team must produce and how many working days
    it will take, based on each team's efficiency.

    NOTE: This system treats all material as owned/committed once produced
    -- there is no generic "idle inventory" buffer to net against. Every
    order's requirement is calculated against full (gross) demand. Actual
    on-hand quantities are tracked separately (see Inventory) purely for
    reporting/visibility, not as an input to this calculation.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return None

    entry_team = (
        db.query(models.Team)
        .filter(models.Team.id == order.entry_team_id)
        .first()
    )
    if not entry_team:
        return None

    teams_in_chain = (
        db.query(models.Team)
        .filter(models.Team.sequence_order <= entry_team.sequence_order)
        .order_by(models.Team.sequence_order.desc())
        .all()
    )

    output_needed = float(order.quantity_requested)
    results = []
    start_date = order.order_date

    for team in teams_in_chain:
        efficiency = float(team.efficiency)
        daily_capacity = float(team.daily_capacity)

        input_needed = output_needed / efficiency
        raw_days_required = (
            math.ceil(output_needed / daily_capacity) if daily_capacity > 0 else 0
        )

        end_date, calendar_days_elapsed, used_default = _count_forward_working_days(
            team.id, start_date, raw_days_required, db
        )

        results.append({
            "team_id": team.id,
            "team_name": team.name,
            "sequence_order": team.sequence_order,
            "output_needed": round(output_needed, 2),
            "input_needed": round(input_needed, 2),
            "efficiency": efficiency,
            "daily_capacity": daily_capacity,
            "working_days_required": raw_days_required,
            "calendar_days_required": calendar_days_elapsed,
            "estimated_completion_date": str(end_date),
            "schedule_data_incomplete": used_default,
        })

        output_needed = input_needed

    return {
        "order_id": order.id,
        "customer_name": order.customer_name,
        "quantity_requested": float(order.quantity_requested),
        "entry_team": entry_team.name,
        "due_date": str(order.due_date) if order.due_date else None,
        "total_raw_material_needed": round(output_needed, 2),
        "steps": results,
    }