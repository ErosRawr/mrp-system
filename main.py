from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date
from calculations import calculate_material_requirements

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
    sells_direct: bool = False,
    db: Session = Depends(get_db),
):
    team = models.Team(
        name=name,
        sequence_order=sequence_order,
        daily_capacity=daily_capacity,
        efficiency=efficiency,
        sells_direct=sells_direct,
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
    return db.query(models.Order).all()

@app.post("/team-weekly-schedule")
def set_weekly_schedule(
    team_id: int,
    day_of_week: int,  # 0=Monday ... 6=Sunday
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