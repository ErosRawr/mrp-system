from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date

import models
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="MRP System", version="0.1.0")


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

@app.post("/team-schedule")
def create_schedule_entry(
    team_id: int,
    date: date,
    is_working_day: bool,
    db: Session = Depends(get_db),
):
    entry = models.TeamSchedule(
        team_id=team_id,
        date=date,
        is_working_day=is_working_day,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/team-schedule")
def list_schedule(db: Session = Depends(get_db)):
    return db.query(models.TeamSchedule).order_by(models.TeamSchedule.date).all()