import models
from main import get_team_occupancy


def test_occupancy_uses_reduced_capacity_in_overall_average(db, make_team, make_order):
    team = make_team(weekly=1000)
    order = make_order(team, qty=500)
    db.add(models.TeamWeekException(
        team_id=team.id,
        year=2026,
        week_number=36,
        capacity_multiplier=0.5,
        reason="Festivo",
    ))
    db.add(models.CapacityAllocation(
        team_id=team.id,
        order_id=order.id,
        year=2026,
        week_number=36,
        quantity_allocated=500,
    ))
    db.commit()

    result = get_team_occupancy(team.id, 2026, 9, db)

    week_36 = next(week for week in result["weekly_breakdown"] if week["week_number"] == 36)
    assert week_36["capacity"] == 500
    assert week_36["occupancy_pct"] == 100.0
    # September 2026 touches five ISO weeks: 4 * 1,000 + 500 effective tons.
    assert result["overall_occupancy_pct"] == 11.1
