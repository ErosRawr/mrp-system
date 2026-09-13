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


class TeamWeekException(Base):
    """
    Marks a specific (team, year, week_number) as having reduced or zero
    availability -- a holiday, a maintenance shutdown, an extended
    weekend, etc. This is the week-level equivalent of "Disponibilidad"
    dropping below normal for a given week.

    capacity_multiplier scales that week's weekly_capacity:
        1.0 = full capacity (the default when no exception exists)
        0.0 = fully unavailable that week
        0.8 = e.g. one holiday out of five working days in that week

    Replaces the earlier day-level TeamWeeklySchedule + TeamScheduleException
    tables, which operated at day granularity and no longer matched the
    week-level planning model the spec requires.
    """
    __tablename__ = "team_week_exception"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    year = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)
    capacity_multiplier = Column(Numeric, nullable=False, default=0)
    reason = Column(String(200), nullable=True)  # e.g. "Día de la Independencia"


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