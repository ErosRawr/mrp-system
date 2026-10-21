"""Regression coverage for reduced weekly capacity in monthly occupancy."""
from tests.helpers import create_order, create_plant, plan


def test_reduced_week_capacity_is_used_in_monthly_occupancy(client):
    create_plant(client)
    client.post("/team-week-exceptions", params=dict(
        team_id=4, year=2026, week_number=39, capacity_multiplier=0.5,
        reason="Festivo",
    ))
    create_order(client, qty=12500, name="Carga completa")
    plan(client, 9)

    result = client.get("/teams/4/occupancy", params=dict(year=2026, month=9)).json()
    week_39 = next(week for week in result["weekly_breakdown"] if week["week_number"] == 39)
    assert week_39["capacity"] == 12500
    assert week_39["occupancy_pct"] == 100.0
    assert result["overall_occupancy_pct"] == 11.1
