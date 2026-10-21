from datetime import date

import models
from planning import run_monthly_planning, _week_end_date


START_WEEK = date(2026, 9, 1).isocalendar()[1]  # ISO week 36


def test_order_spills_across_weeks(db, make_team, make_order):
    team = make_team(weekly=1000)
    order = make_order(team, qty=2500)

    run_monthly_planning(2026, 9, db)
    db.refresh(order)

    assert order.calculated_delivery_date == _week_end_date(2026, START_WEEK + 2)


def test_reduced_week_pushes_delivery_later(db, make_team, make_order):
    team = make_team(weekly=1000)
    db.add(models.TeamWeekException(
        team_id=team.id,
        year=2026,
        week_number=START_WEEK,
        capacity_multiplier=0.5,
        reason="Festivo",
    ))
    db.commit()
    order = make_order(team, qty=1000)

    run_monthly_planning(2026, 9, db)
    db.refresh(order)

    # Week 36 has 500 t available; the other 500 t moves to week 37.
    assert order.calculated_delivery_date == _week_end_date(2026, START_WEEK + 1)


def test_zero_capacity_week_is_skipped(db, make_team, make_order):
    team = make_team(weekly=1000)
    db.add(models.TeamWeekException(
        team_id=team.id,
        year=2026,
        week_number=START_WEEK,
        capacity_multiplier=0.0,
        reason="Paro",
    ))
    db.commit()
    order = make_order(team, qty=1000)

    run_monthly_planning(2026, 9, db)
    db.refresh(order)

    assert order.calculated_delivery_date == _week_end_date(2026, START_WEEK + 1)


def test_allocation_never_exceeds_effective_capacity(db, make_team, make_order):
    team = make_team(weekly=1000)
    db.add(models.TeamWeekException(
        team_id=team.id,
        year=2026,
        week_number=START_WEEK,
        capacity_multiplier=0.8,
    ))
    db.commit()
    make_order(team, qty=3000)

    run_monthly_planning(2026, 9, db)
    allocations = db.query(models.CapacityAllocation).filter_by(
        team_id=team.id,
        year=2026,
        week_number=START_WEEK,
    ).all()

    assert sum(float(allocation.quantity_allocated) for allocation in allocations) <= 800 + 1e-6


def test_priority_order_jumps_the_queue(db, make_team, make_order):
    team = make_team(weekly=1000)
    early = make_order(team, qty=1000, requested=date(2026, 9, 5))
    vip = make_order(team, qty=1000, requested=date(2026, 9, 28), priority=True)

    run_monthly_planning(2026, 9, db, criterion="peps")
    db.refresh(early)
    db.refresh(vip)
    assert early.calculated_delivery_date < vip.calculated_delivery_date

    run_monthly_planning(2026, 9, db, criterion="prioritario")
    db.refresh(early)
    db.refresh(vip)
    assert vip.calculated_delivery_date < early.calculated_delivery_date
