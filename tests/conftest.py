import os
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Importing main.py creates its configured tables. Keep tests completely
# isolated from a developer's mrp.db, even if they have a local URL configured.
os.environ["MRP_DATABASE_URL"] = "sqlite://"

from database import Base
import models


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def make_team(db):
    def _make(weekly=1000, efficiency=1.0, seq=1):
        team = models.Team(
            name=f"T{seq}",
            sequence_order=seq,
            monthly_capacity=weekly * 4,
            weeks_available=4,
            efficiency=efficiency,
        )
        db.add(team)
        db.commit()
        db.refresh(team)
        return team
    return _make


@pytest.fixture
def make_order(db):
    def _make(team, qty, requested=None, priority=False, order_date=date(2026, 9, 1)):
        order = models.Order(
            customer_name="Cliente",
            quantity_requested=qty,
            entry_team_id=team.id,
            order_date=order_date,
            requested_delivery_date=requested,
            planning_year=order_date.year,
            planning_month=order_date.month,
            is_priority=priority,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order
    return _make
