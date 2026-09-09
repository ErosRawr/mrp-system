from sqlalchemy import Column, Integer, String, Numeric, Boolean, Date, ForeignKey
from database import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    sequence_order = Column(Integer, nullable=False, unique=True)
    daily_capacity = Column(Numeric, nullable=False)
    efficiency = Column(Numeric, nullable=False)  # e.g. 0.95 = 95%


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), nullable=False)
    quantity_requested = Column(Numeric, nullable=False)
    entry_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    order_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)


class TeamWeeklySchedule(Base):
    """Recurring weekly pattern: does this team normally work on this weekday?"""
    __tablename__ = "team_weekly_schedule"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    is_working_day = Column(Boolean, nullable=False, default=True)


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, unique=True)
    quantity_on_hand = Column(Numeric, nullable=False, default=0)


class CapacityAllocation(Base):
    """
    Tracks how much of a team's daily_capacity has already been claimed
    by a specific order on a specific date. This is what makes scheduling
    real: instead of every order assuming a team is fully free, we check
    remaining capacity = team.daily_capacity - sum(allocations for that date).
    """
    __tablename__ = "capacity_allocation"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    date = Column(Date, nullable=False)
    quantity_allocated = Column(Numeric, nullable=False)