from sqlalchemy import Column, Integer, String, Numeric, Boolean, Date, ForeignKey
from database import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    sequence_order = Column(Integer, nullable=False, unique=True)
    monthly_capacity = Column(Numeric, nullable=False)  # "Capacidad Mensual"
    weeks_available = Column(Integer, nullable=False, default=4)  # "Disponibilidad"
    efficiency = Column(Numeric, nullable=False)  # "Rendimiento", e.g. 0.95 = 95%

    @property
    def weekly_capacity(self):
        """Monthly capacity spread evenly across the available weeks."""
        if self.weeks_available <= 0:
            return 0
        return float(self.monthly_capacity) / self.weeks_available


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), nullable=False)
    quantity_requested = Column(Numeric, nullable=False)
    entry_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    order_date = Column(Date, nullable=False)  # when the order was placed/registered

    # "fecha solicitada de entrega" -- what the customer asked for
    requested_delivery_date = Column(Date, nullable=True)

    # Which month this order belongs to for planning purposes. Set at
    # creation from order_date, but kept explicit since the spec plans
    # "all orders for the month" as a distinct batch concept.
    planning_year = Column(Integer, nullable=False)
    planning_month = Column(Integer, nullable=False)  # 1-12

    # Filled in by the planning run -- the actual computed delivery date
    # (as a week-ending date) once capacity has been allocated. Null until
    # the order has been through a planning run.
    calculated_delivery_date = Column(Date, nullable=True)


class TeamWeeklySchedule(Base):
    """Recurring weekly pattern: does this team normally work on this weekday?
    Kept for finer-grained day-level scheduling if needed alongside the
    week-level planning run."""
    __tablename__ = "team_weekly_schedule"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    is_working_day = Column(Boolean, nullable=False, default=True)


class TeamScheduleException(Base):
    """One-off override for a specific date, layered on top of the recurring
    weekly pattern."""
    __tablename__ = "team_schedule_exception"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    date = Column(Date, nullable=False)
    is_working_day = Column(Boolean, nullable=False)
    reason = Column(String(200), nullable=True)


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, unique=True)
    quantity_on_hand = Column(Numeric, nullable=False, default=0)


class CapacityAllocation(Base):
    """
    Tracks how much of a team's WEEKLY capacity has already been claimed
    by a specific order, for a specific (year, week_number). This is the
    week-level equivalent of a day-level ledger: remaining capacity for a
    week = team.weekly_capacity - sum(allocations for that team/year/week).
    """
    __tablename__ = "capacity_allocation"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    year = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)  # ISO week number
    quantity_allocated = Column(Numeric, nullable=False)