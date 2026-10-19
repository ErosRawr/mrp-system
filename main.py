from calendar import monthrange
from datetime import date, timedelta

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

import models
from calculations import calculate_material_requirements
from database import engine, get_db
from disruptions import draw_disruptions, DEFAULT_PROBABILITY, DEFAULT_MIN_DROP, DEFAULT_MAX_DROP
from lateness import classify_lateness
from mexican_holidays import get_holiday_week_impact
from planning import run_monthly_planning, compare_planning_criteria, replan_all

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="MRP System", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def health_check_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}


@app.post("/teams")
def create_team(
    name: str,
    sequence_order: int,
    monthly_capacity: float,
    efficiency: float,
    weeks_available: int = 4,
    holiday_staffing: float = 0.0,
    db: Session = Depends(get_db),
):
    if not (0 <= holiday_staffing <= 1):
        raise HTTPException(400, "holiday_staffing must be between 0 (team stops on holidays) and 1 (runs normally)")
    if monthly_capacity <= 0:
        raise HTTPException(400, "monthly_capacity must be greater than 0 -- a team with no capacity can never produce anything")
    if weeks_available <= 0:
        raise HTTPException(400, "weeks_available must be greater than 0")
    if not (0 < efficiency <= 1):
        raise HTTPException(400, "efficiency must be between 0 (exclusive) and 1 (inclusive), e.g. 0.95 for 95%")

    existing = db.query(models.Team).filter(models.Team.sequence_order == sequence_order).first()
    if existing:
        raise HTTPException(400, f"sequence_order {sequence_order} is already used by team '{existing.name}'")

    team = models.Team(
        name=name,
        sequence_order=sequence_order,
        monthly_capacity=monthly_capacity,
        weeks_available=weeks_available,
        efficiency=efficiency,
        holiday_staffing=holiday_staffing,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@app.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    teams = db.query(models.Team).order_by(models.Team.sequence_order).all()
    # Include the computed weekly_capacity in the response for convenience,
    # since it's a @property and not a real column.
    return [
        {
            "id": t.id,
            "name": t.name,
            "sequence_order": t.sequence_order,
            "monthly_capacity": float(t.monthly_capacity),
            "weeks_available": t.weeks_available,
            "weekly_capacity": t.weekly_capacity,
            "efficiency": float(t.efficiency),
            "holiday_staffing": float(t.holiday_staffing),
        }
        for t in teams
    ]


@app.post("/orders")
def create_order(
    customer_name: str,
    quantity_requested: float,
    entry_team_id: int,
    order_date: date,
    requested_delivery_date: date = None,
    planning_year: int = None,
    planning_month: int = None,
    is_priority: bool = False,
    tipo_pedido: str = None,
    db: Session = Depends(get_db),
):
    if quantity_requested <= 0:
        raise HTTPException(400, "quantity_requested must be greater than 0")

    entry_team = db.query(models.Team).filter(models.Team.id == entry_team_id).first()
    if not entry_team:
        raise HTTPException(400, f"No team exists with id {entry_team_id} -- check GET /teams for valid ids")

    if requested_delivery_date and requested_delivery_date < order_date:
        raise HTTPException(400, "requested_delivery_date cannot be before order_date")

    # Default the planning period to the order's own month/year unless the
    # caller explicitly overrides it (e.g. planning next month's orders
    # ahead of time).
    if planning_year is None:
        planning_year = order_date.year
    if planning_month is None:
        planning_month = order_date.month

    order = models.Order(
        customer_name=customer_name,
        quantity_requested=quantity_requested,
        entry_team_id=entry_team_id,
        order_date=order_date,
        requested_delivery_date=requested_delivery_date,
        planning_year=planning_year,
        planning_month=planning_month,
        is_priority=is_priority,
        tipo_pedido=tipo_pedido,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders")
def list_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).order_by(models.Order.order_date).all()
    result = []
    for o in orders:
        days_late, status, is_late = classify_lateness(
            o.calculated_delivery_date, o.requested_delivery_date
        )
        result.append({
            "id": o.id,
            "customer_name": o.customer_name,
            "quantity_requested": o.quantity_requested,
            "entry_team_id": o.entry_team_id,
            "order_date": o.order_date,
            "requested_delivery_date": o.requested_delivery_date,
            "planning_year": o.planning_year,
            "planning_month": o.planning_month,
            "calculated_delivery_date": o.calculated_delivery_date,
            "is_priority": o.is_priority,
            "tipo_pedido": o.tipo_pedido,
            "days_late": days_late,
            "lateness_status": status,
            "is_late": is_late,
        })
    return result


@app.put("/orders/{order_id}")
def update_order(
    order_id: int,
    customer_name: str = None,
    quantity_requested: float = None,
    entry_team_id: int = None,
    order_date: date = None,
    requested_delivery_date: date = None,
    planning_year: int = None,
    planning_month: int = None,
    is_priority: bool = None,
    tipo_pedido: str = None,
    db: Session = Depends(get_db),
):
    """
    Updates any subset of an order's fields. Since a prior planning run's
    CapacityAllocation rows and calculated_delivery_date reflect the OLD
    values, any edit clears both -- the order reverts to "not yet planned"
    until the monthly planning run is executed again.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    if quantity_requested is not None:
        if quantity_requested <= 0:
            raise HTTPException(400, "quantity_requested must be greater than 0")
        order.quantity_requested = quantity_requested

    if entry_team_id is not None:
        entry_team = db.query(models.Team).filter(models.Team.id == entry_team_id).first()
        if not entry_team:
            raise HTTPException(400, f"No team exists with id {entry_team_id}")
        order.entry_team_id = entry_team_id

    if customer_name is not None:
        order.customer_name = customer_name
    if order_date is not None:
        order.order_date = order_date
    if requested_delivery_date is not None:
        order.requested_delivery_date = requested_delivery_date
    if planning_year is not None:
        order.planning_year = planning_year
    if planning_month is not None:
        order.planning_month = planning_month
    if is_priority is not None:
        order.is_priority = is_priority
    if tipo_pedido is not None:
        order.tipo_pedido = tipo_pedido

    final_order_date = order_date if order_date is not None else order.order_date
    final_due_date = requested_delivery_date if requested_delivery_date is not None else order.requested_delivery_date
    if final_due_date and final_due_date < final_order_date:
        raise HTTPException(400, "requested_delivery_date cannot be before order_date")

    # Clear stale planning results -- any past CapacityAllocation for this
    # order no longer reflects its current quantity/team/dates.
    db.query(models.CapacityAllocation).filter(
        models.CapacityAllocation.order_id == order_id
    ).delete(synchronize_session=False)
    order.calculated_delivery_date = None

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    # Clean up any CapacityAllocation rows this order claimed, so deleting
    # an order actually frees the capacity for other orders on re-planning.
    db.query(models.CapacityAllocation).filter(
        models.CapacityAllocation.order_id == order_id
    ).delete(synchronize_session=False)

    db.delete(order)
    db.commit()
    return {"status": "deleted", "id": order_id}


@app.post("/team-week-exceptions")
def set_week_exception(
    team_id: int,
    year: int,
    week_number: int,
    capacity_multiplier: float,
    reason: str = None,
    db: Session = Depends(get_db),
):
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(400, f"No team exists with id {team_id} -- check GET /teams for valid ids")
    if not (1 <= week_number <= 53):
        raise HTTPException(400, "week_number must be between 1 and 53 (ISO week numbering)")
    if not (0 <= capacity_multiplier <= 1):
        raise HTTPException(400, "capacity_multiplier must be between 0 and 1")

    existing = db.query(models.TeamWeekException).filter(
        models.TeamWeekException.team_id == team_id,
        models.TeamWeekException.year == year,
        models.TeamWeekException.week_number == week_number,
    ).first()
    if existing:
        existing.capacity_multiplier = capacity_multiplier
        existing.reason = reason
        db.commit()
        db.refresh(existing)
        return existing

    entry = models.TeamWeekException(
        team_id=team_id, year=year, week_number=week_number,
        capacity_multiplier=capacity_multiplier, reason=reason,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/team-week-exceptions")
def list_week_exceptions(db: Session = Depends(get_db)):
    return (
        db.query(models.TeamWeekException)
        .order_by(models.TeamWeekException.year, models.TeamWeekException.week_number)
        .all()
    )


@app.delete("/team-week-exceptions/{exception_id}")
def delete_week_exception(exception_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.TeamWeekException).filter(
        models.TeamWeekException.id == exception_id
    ).first()
    if not entry:
        raise HTTPException(404, "Exception not found")
    db.delete(entry)
    db.commit()
    return {"status": "deleted", "id": exception_id}


def _reduce_week_capacity(db: Session, team_id: int, year: int, week_number: int,
                          reduction: float, reason: str, tag: str):
    """
    Lowers one team-week's capacity_multiplier by `reduction`, stacking on any
    existing exception (a 0.9 maintenance week plus a 0.2 holiday -> 0.7).

    Returns the row, or None when the week's reason already contains `tag`:
    that cause was applied before, so re-running an import or a generator
    does not stack it a second time.
    """
    existing = db.query(models.TeamWeekException).filter(
        models.TeamWeekException.team_id == team_id,
        models.TeamWeekException.year == year,
        models.TeamWeekException.week_number == week_number,
    ).first()

    if existing:
        if existing.reason and tag in existing.reason:
            return None
        existing.capacity_multiplier = max(float(existing.capacity_multiplier) - reduction, 0.0)
        existing.reason = f"{existing.reason}; {reason}" if existing.reason else reason
        db.add(existing)
        return existing

    entry = models.TeamWeekException(
        team_id=team_id, year=year, week_number=week_number,
        capacity_multiplier=max(1.0 - reduction, 0.0), reason=reason,
    )
    db.add(entry)
    return entry


@app.post("/team-week-exceptions/import-mexican-holidays")
def import_mexican_holidays(
    team_id: int,
    year: int,
    working_days_per_week: int = 5,
    db: Session = Depends(get_db),
):
    """
    Generates TeamWeekException rows for every Mexican federal holiday in
    the given year, for the given team.

    How much a holiday costs depends on the team's `holiday_staffing`:
    the share of a normal day's capacity that still runs on a holiday.
        staffing 0.0 (team stops)    -> one holiday in a 5-day week = multiplier 0.8
        staffing 0.5 (skeleton crew) -> multiplier 0.9
        staffing 1.0 (continuous)    -> no change, no row created
    Multiple holidays in the same week stack. If a week already has an
    exception, the reduction is ADDED to it. Re-running is safe: a holiday
    already recorded in a week's reason is not applied twice.
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    if not (1970 <= year <= 2200):
        raise HTTPException(400, "year must be a realistic calendar year (1970-2200)")
    if working_days_per_week <= 0:
        raise HTTPException(400, "working_days_per_week must be greater than 0")

    staffing = float(team.holiday_staffing)
    reduction_per_holiday = (1.0 / working_days_per_week) * (1.0 - staffing)
    holiday_impact = get_holiday_week_impact(year, working_days_per_week)

    created = []
    if reduction_per_holiday > 0:
        for (iso_year, iso_week), descriptions in holiday_impact.items():
            reduction = min(reduction_per_holiday * len(descriptions), 1.0)
            reason_text = ", ".join(descriptions)
            entry = _reduce_week_capacity(db, team_id, iso_year, iso_week, reduction, reason_text, reason_text)
            if entry is not None:
                created.append(entry)

    db.commit()
    for entry in created:
        db.refresh(entry)

    return {
        "team_id": team_id,
        "year": year,
        "holiday_staffing": staffing,
        "holidays_imported": len(created),
        "exceptions": created,
    }


@app.post("/team-week-exceptions/generate-disruptions")
def generate_disruptions(
    year: int,
    probability: float = DEFAULT_PROBABILITY,
    min_drop: float = DEFAULT_MIN_DROP,
    max_drop: float = DEFAULT_MAX_DROP,
    seed: int = None,
    team_id: int = None,
    db: Session = Depends(get_db),
):
    """
    Random productivity drops. Every team (or just `team_id`) has a
    `probability` chance (default 10%) of a drop in each ISO week of `year`;
    a hit removes between `min_drop` and `max_drop` of that week's capacity
    (default 10% to 40%). Hits are stored as ordinary week exceptions, so the
    calendar, occupancy and planner all see them.

    Pass `seed` to make the draw reproducible. Re-running with the same seed
    changes nothing (weeks already hit are skipped); a different seed adds the
    new weeks it picks. Plans already committed do not know about new
    exceptions -- call POST /planning/replan-all afterwards.
    """
    if not (0 <= probability <= 1):
        raise HTTPException(400, "probability must be between 0 and 1, e.g. 0.10 for 10%")
    if not (0 < min_drop <= max_drop <= 1):
        raise HTTPException(400, "drops must satisfy 0 < min_drop <= max_drop <= 1")
    if not (1970 <= year <= 2200):
        raise HTTPException(400, "year must be a realistic calendar year (1970-2200)")

    if team_id is not None:
        if not db.query(models.Team).filter(models.Team.id == team_id).first():
            raise HTTPException(404, "Team not found")
        team_ids = [team_id]
    else:
        team_ids = [t.id for t in db.query(models.Team).order_by(models.Team.sequence_order).all()]

    hits = draw_disruptions(team_ids, probability, min_drop, max_drop, seed=seed)

    created = []
    for tid, week, drop in hits:
        reason = f"Baja de productividad (-{round(drop * 100)}%)"
        entry = _reduce_week_capacity(db, tid, year, week, drop, reason, "Baja de productividad")
        if entry is not None:
            created.append(entry)

    db.commit()
    for entry in created:
        db.refresh(entry)

    by_team = {}
    for entry in created:
        by_team[entry.team_id] = by_team.get(entry.team_id, 0) + 1

    return {
        "year": year,
        "probability": probability,
        "seed": seed,
        "weeks_affected": len(created),
        "by_team": by_team,
        "exceptions": created,
    }


@app.get("/orders/{order_id}/requirements")
def get_order_requirements(order_id: int, db: Session = Depends(get_db)):
    """
    Pure material calculation -- how much each team needs to produce.
    No dates, no capacity contention. This runs immediately when an order
    is registered, independent of the monthly planning run.
    """
    result = calculate_material_requirements(order_id, db)
    if result is None:
        return {"error": "Order or entry team not found"}
    return result


@app.post("/planning/run")
def trigger_monthly_planning(
    year: int, month: int,
    criterion: str = "peps",
    db: Session = Depends(get_db),
):
    """
    The core spec requirement: runs the monthly planning process. Takes
    every order registered for (year, month), sorts according to
    `criterion` (peps, prioritario, or heuristica -- see heuristics.py),
    and walks each one through the full team chain, consuming each
    team's weekly capacity so orders queue realistically against each
    other and against whatever capacity remains.

    Writes calculated_delivery_date back onto each order and commits the
    underlying CapacityAllocation rows. Idempotent -- re-running for the
    same month clears prior allocations for that month's orders first.
    """
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be between 1 and 12")
    if criterion not in ("peps", "prioritario", "heuristica"):
        raise HTTPException(400, "criterion must be one of: peps, prioritario, heuristica")

    result = run_monthly_planning(year, month, db, criterion=criterion)
    return result


@app.get("/planning/compare")
def compare_planning(year: int, month: int, db: Session = Depends(get_db)):
    """
    Runs all three planning criteria (peps, prioritario, heuristica) for
    the given month WITHOUT committing any of them -- lets you compare
    how each strategy would schedule the month's orders before choosing
    one to actually run for real via POST /planning/run.
    """
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be between 1 and 12")

    result = compare_planning_criteria(year, month, db)
    return result


@app.post("/planning/replan-all")
def replan_everything(db: Session = Depends(get_db)):
    """
    Re-plans every planned month from the earliest one, in calendar order,
    each with the criterion it was last run with. Use it after changing
    availability (week exceptions, holidays, disruptions, team capacity),
    because plans already committed do not update on their own.
    """
    return replan_all(db)


@app.get("/planning/months")
def list_planned_months(db: Session = Depends(get_db)):
    """The months that have been planned, and the criterion each was run with."""
    rows = (
        db.query(models.MonthPlan)
        .order_by(models.MonthPlan.planning_year, models.MonthPlan.planning_month)
        .all()
    )
    return [
        {"planning_year": r.planning_year, "planning_month": r.planning_month, "criterion": r.criterion}
        for r in rows
    ]


@app.get("/teams/{team_id}/capacity-allocations")
def list_capacity_allocations(team_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.CapacityAllocation)
        .filter(models.CapacityAllocation.team_id == team_id)
        .order_by(models.CapacityAllocation.year, models.CapacityAllocation.week_number)
        .all()
    )


@app.get("/teams/{team_id}/occupancy")
def get_team_occupancy(team_id: int, year: int, month: int, db: Session = Depends(get_db)):
    """
    Returns this team's percentage occupancy for the given month, plus a
    week-by-week breakdown -- the chart data required by the spec.
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")

    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # Every ISO (year, week) this calendar month touches, day by day
    # (handles months that spill into adjacent ISO years/weeks at the edges).
    all_weeks = set()
    d = first_day
    while d <= last_day:
        iso_year, iso_week, _ = d.isocalendar()
        all_weeks.add((iso_year, iso_week))
        d += timedelta(days=1)

    weekly_capacity = team.weekly_capacity
    breakdown = []
    total_allocated = 0.0
    total_capacity = 0.0

    for iso_year, iso_week in sorted(all_weeks):
        allocated = (
            db.query(models.CapacityAllocation)
            .filter(
                models.CapacityAllocation.team_id == team_id,
                models.CapacityAllocation.year == iso_year,
                models.CapacityAllocation.week_number == iso_week,
            )
            .all()
        )
        week_total = sum(float(a.quantity_allocated) for a in allocated)

        exception = (
            db.query(models.TeamWeekException)
            .filter(
                models.TeamWeekException.team_id == team_id,
                models.TeamWeekException.year == iso_year,
                models.TeamWeekException.week_number == iso_week,
            )
            .first()
        )
        multiplier = float(exception.capacity_multiplier) if exception else 1.0
        effective_capacity = weekly_capacity * multiplier
        total_allocated += week_total
        total_capacity += effective_capacity

        breakdown.append({
            "year": iso_year,
            "week_number": iso_week,
            "allocated": round(week_total, 2),
            "capacity": round(effective_capacity, 2),
            "capacity_multiplier": multiplier,
            "reason": exception.reason if exception else None,
            "occupancy_pct": round((week_total / effective_capacity) * 100, 1) if effective_capacity > 0 else None,
        })

    overall_pct = round((total_allocated / total_capacity) * 100, 1) if total_capacity > 0 else None

    return {
        "team_id": team.id,
        "team_name": team.name,
        "year": year,
        "month": month,
        "overall_occupancy_pct": overall_pct,
        "weekly_breakdown": breakdown,
    }
