from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, timedelta
from calculations import calculate_material_requirements
from scheduling import schedule_team_capacity

import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MRP System", version="0.1.0")

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
    daily_capacity: float,
    efficiency: float,
    db: Session = Depends(get_db),
):
    if daily_capacity <= 0:
        raise HTTPException(400, "daily_capacity must be greater than 0 -- a team with no capacity can never produce anything")
    if not (0 < efficiency <= 1):
        raise HTTPException(400, "efficiency must be between 0 (exclusive) and 1 (inclusive), e.g. 0.95 for 95%")

    existing = db.query(models.Team).filter(models.Team.sequence_order == sequence_order).first()
    if existing:
        raise HTTPException(400, f"sequence_order {sequence_order} is already used by team '{existing.name}'")

    team = models.Team(
        name=name,
        sequence_order=sequence_order,
        daily_capacity=daily_capacity,
        efficiency=efficiency,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@app.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    return db.query(models.Team).order_by(models.Team.sequence_order).all()


@app.post("/orders")
def create_order(
    customer_name: str,
    quantity_requested: float,
    entry_team_id: int,
    order_date: date,
    due_date: date = None,
    db: Session = Depends(get_db),
):
    if quantity_requested <= 0:
        raise HTTPException(400, "quantity_requested must be greater than 0")

    entry_team = db.query(models.Team).filter(models.Team.id == entry_team_id).first()
    if not entry_team:
        raise HTTPException(400, f"No team exists with id {entry_team_id} -- check GET /teams for valid ids")

    if due_date and due_date < order_date:
        raise HTTPException(400, "due_date cannot be before order_date")

    order = models.Order(
        customer_name=customer_name,
        quantity_requested=quantity_requested,
        entry_team_id=entry_team_id,
        order_date=order_date,
        due_date=due_date,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders")
def list_orders(db: Session = Depends(get_db)):
    return db.query(models.Order).order_by(models.Order.order_date).all()


@app.post("/team-weekly-schedule")
def set_weekly_schedule(
    team_id: int,
    day_of_week: int,
    is_working_day: bool,
    db: Session = Depends(get_db),
):
    existing = db.query(models.TeamWeeklySchedule).filter(
        models.TeamWeeklySchedule.team_id == team_id,
        models.TeamWeeklySchedule.day_of_week == day_of_week,
    ).first()
    if existing:
        existing.is_working_day = is_working_day
        db.commit()
        db.refresh(existing)
        return existing

    entry = models.TeamWeeklySchedule(
        team_id=team_id, day_of_week=day_of_week, is_working_day=is_working_day
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/team-weekly-schedule")
def list_weekly_schedule(db: Session = Depends(get_db)):
    return db.query(models.TeamWeeklySchedule).all()


@app.post("/team-schedule-exceptions")
def set_schedule_exception(
    team_id: int,
    date: date,
    is_working_day: bool,
    reason: str = None,
    db: Session = Depends(get_db),
):
    existing = db.query(models.TeamScheduleException).filter(
        models.TeamScheduleException.team_id == team_id,
        models.TeamScheduleException.date == date,
    ).first()
    if existing:
        existing.is_working_day = is_working_day
        existing.reason = reason
        db.commit()
        db.refresh(existing)
        return existing

    entry = models.TeamScheduleException(
        team_id=team_id, date=date, is_working_day=is_working_day, reason=reason
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/team-schedule-exceptions")
def list_schedule_exceptions(db: Session = Depends(get_db)):
    return (
        db.query(models.TeamScheduleException)
        .order_by(models.TeamScheduleException.date)
        .all()
    )


@app.delete("/team-schedule-exceptions/{exception_id}")
def delete_schedule_exception(exception_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.TeamScheduleException).filter(
        models.TeamScheduleException.id == exception_id
    ).first()
    if not entry:
        return {"error": "Exception not found"}
    db.delete(entry)
    db.commit()
    return {"status": "deleted", "id": exception_id}


@app.get("/orders/{order_id}/requirements")
def get_order_requirements(order_id: int, db: Session = Depends(get_db)):
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


@app.post("/orders/{order_id}/schedule")
def schedule_order(order_id: int, db: Session = Depends(get_db)):
    """
    Runs the material requirements calculation, then schedules capacity
    for each team in the chain -- CHAINED in time. The upstream-most team
    (e.g. Melting) starts on order_date. Each subsequent (downstream) team
    can only start once the previous team's output for this order is
    actually ready, i.e. after the previous team's end_date.

    Returns the earliest realistic completion date for the order: the
    end_date of the LAST team in the chain (the entry team).

    FIFO across orders is enforced by scheduling orders in sequence --
    call this endpoint for orders in order_date / creation order, since
    each call commits CapacityAllocation rows that all later calls see.
    """
    requirements = calculate_material_requirements(order_id, db)
    if requirements is None:
        return {"error": "Order or entry team not found"}

    order = db.query(models.Order).filter(models.Order.id == order_id).first()

    # requirements["steps"] is ordered entry-team-first, upstream-last
    # (e.g. Finishing, Hot Rolling, Casting, Melting). For time-chaining
    # we need to walk it in PRODUCTION order instead: Melting first,
    # Finishing last -- so we reverse it here.
    steps_in_production_order = list(reversed(requirements["steps"]))

    schedule_results = []
    next_start_date = order.order_date

    for step in steps_in_production_order:
        result = schedule_team_capacity(
            team_id=step["team_id"],
            order_id=order_id,
            quantity_needed=step["output_needed"],
            start_date=next_start_date,
            db=db,
            commit=True,
        )
        schedule_results.append({
            "team_id": step["team_id"],
            "team_name": step["team_name"],
            **result,
        })

        # The next (downstream) team can't start until this team's
        # output is ready -- i.e. the day after this team finishes.
        end_date_str = result["end_date"]
        end_date = date.fromisoformat(end_date_str)
        next_start_date = end_date + timedelta(days=1)

    earliest_completion_date = schedule_results[-1]["end_date"] if schedule_results else None

    return {
        "order_id": order_id,
        "customer_name": requirements["customer_name"],
        "quantity_requested": requirements["quantity_requested"],
        "requested_due_date": requirements["due_date"],
        "earliest_possible_completion_date": earliest_completion_date,
        "schedule": schedule_results,
    }


@app.get("/teams/{team_id}/capacity-allocations")
def list_capacity_allocations(team_id: int, db: Session = Depends(get_db)):
    return (
        db.query(models.CapacityAllocation)
        .filter(models.CapacityAllocation.team_id == team_id)
        .order_by(models.CapacityAllocation.date)
        .all()
    )