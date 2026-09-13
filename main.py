from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date
from calculations import calculate_material_requirements
from planning import run_monthly_planning
from mexican_holidays import get_holiday_week_impact

import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

from fastapi.middleware.cors import CORSMiddleware

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
    db: Session = Depends(get_db),
):
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
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders")
def list_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).order_by(models.Order.order_date).all()


@app.post("/team-week-exceptions")
def set_week_exception(
    team_id: int,
    year: int,
    week_number: int,
    capacity_multiplier: float,
    reason: str = None,
    db: Session = Depends(get_db),
):
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
        return {"error": "Exception not found"}
    db.delete(entry)
    db.commit()
    return {"status": "deleted", "id": exception_id}


@app.post("/team-week-exceptions/import-mexican-holidays")
def import_mexican_holidays(
    team_id: int,
    year: int,
    working_days_per_week: int = 5,
    db: Session = Depends(get_db),
):
    """
    Generates TeamWeekException rows for every Mexican federal holiday in
    the given year, for the given team. Each holiday reduces that week's
    capacity_multiplier proportionally: one holiday in a 5-day working
    week -> multiplier 0.8 (4/5 of the week remains available). Multiple
    holidays in the same week stack (rare, but handled).

    If a week already has an exception set, this ADDS to the reduction
    rather than overwriting -- e.g. a week with an existing 0.9 multiplier
    (partial maintenance) and a holiday would become 0.9 - 0.2 = 0.7.
    """
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    if working_days_per_week <= 0:
        raise HTTPException(400, "working_days_per_week must be greater than 0")

    holiday_impact = get_holiday_week_impact(year, working_days_per_week)
    reduction_per_holiday = 1.0 / working_days_per_week

    created = []
    for (iso_year, iso_week), descriptions in holiday_impact.items():
        reduction = min(reduction_per_holiday * len(descriptions), 1.0)

        existing = db.query(models.TeamWeekException).filter(
            models.TeamWeekException.team_id == team_id,
            models.TeamWeekException.year == iso_year,
            models.TeamWeekException.week_number == iso_week,
        ).first()

        reason_text = ", ".join(descriptions)

        if existing:
            new_multiplier = max(float(existing.capacity_multiplier) - reduction, 0.0)
            existing.capacity_multiplier = new_multiplier
            existing.reason = f"{existing.reason}; {reason_text}" if existing.reason else reason_text
            db.add(existing)
            created.append(existing)
        else:
            new_multiplier = max(1.0 - reduction, 0.0)
            entry = models.TeamWeekException(
                team_id=team_id, year=iso_year, week_number=iso_week,
                capacity_multiplier=new_multiplier, reason=reason_text,
            )
            db.add(entry)
            created.append(entry)

    db.commit()
    for entry in created:
        db.refresh(entry)

    return {
        "team_id": team_id,
        "year": year,
        "holidays_imported": len(created),
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


@app.post("/inventory")
def set_inventory(
    team_id: int,
    quantity_on_hand: float,
    db: Session = Depends(get_db),
):
    existing = db.query(models.Inventory).filter(
        models.Inventory.team_id == team_id
    ).first()
    if existing:
        existing.quantity_on_hand = quantity_on_hand
        db.commit()
        db.refresh(existing)
        return existing

    entry = models.Inventory(team_id=team_id, quantity_on_hand=quantity_on_hand)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/inventory")
def list_inventory(db: Session = Depends(get_db)):
    return db.query(models.Inventory).all()


@app.post("/planning/run")
def trigger_monthly_planning(year: int, month: int, db: Session = Depends(get_db)):
    """
    The core spec requirement: runs the monthly planning process. Takes
    every order registered for (year, month), sorts by requested delivery
    date, and walks each one through the full team chain, consuming each
    team's weekly capacity so orders queue realistically against each
    other and against whatever capacity remains.

    Writes calculated_delivery_date back onto each order and commits the
    underlying CapacityAllocation rows. Safe to re-run for the same month
    only if you understand it will add NEW allocations on top of any
    already committed by a prior run for the same orders -- for a clean
    re-run, allocations for that month's orders should be cleared first
    (not yet implemented; run once per month per this MVP).
    """
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be between 1 and 12")

    result = run_monthly_planning(year, month, db)
    return result


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

    # Determine which ISO weeks fall in this calendar month.
    from calendar import monthrange
    from datetime import date as date_cls

    first_day = date_cls(year, month, 1)
    last_day = date_cls(year, month, monthrange(year, month)[1])

    weeks_in_month = sorted(set(
        first_day.isocalendar()[1] if d == first_day else d.isocalendar()[1]
        for d in [first_day, last_day]
    ))
    # Build the actual set of ISO weeks touched by this month, day by day
    # (handles months that span into adjacent ISO years/weeks at the edges).
    from datetime import timedelta
    all_weeks = set()
    d = first_day
    while d <= last_day:
        iso_year, iso_week, _ = d.isocalendar()
        all_weeks.add((iso_year, iso_week))
        d += timedelta(days=1)

    weekly_capacity = team.weekly_capacity
    breakdown = []
    total_allocated = 0.0

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

        breakdown.append({
            "year": iso_year,
            "week_number": iso_week,
            "allocated": round(week_total, 2),
            "capacity": round(effective_capacity, 2),
            "capacity_multiplier": multiplier,
            "reason": exception.reason if exception else None,
            "occupancy_pct": round((week_total / effective_capacity) * 100, 1) if effective_capacity > 0 else None,
        })

    total_capacity = weekly_capacity * len(all_weeks)
    overall_pct = round((total_allocated / total_capacity) * 100, 1) if total_capacity > 0 else None

    return {
        "team_id": team.id,
        "team_name": team.name,
        "year": year,
        "month": month,
        "overall_occupancy_pct": overall_pct,
        "weekly_breakdown": breakdown,
    }