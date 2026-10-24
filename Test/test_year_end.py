"""ISO years have 52 or 53 weeks; the planner must walk every one of them, no more and no fewer."""
from datetime import date

from helpers import allocations_by_team_week, create_order, create_plant, plan


def test_week_53_is_used_in_a_53_week_year(client):
    create_plant(client)
    create_order(client, qty=500, lead_days=40, order_date=date(2026, 12, 14), name="fin de año")
    result = plan(client, 12)["results"][0]
    # Equipo 1 week 51, Equipo 2 week 52, Equipo 3 week 53 (2026 has 53 ISO weeks), Equipo 4 week 1 of 2027
    assert result["calculated_delivery_date"] == "2027-01-10"
    assert (3, 2026, 53) in allocations_by_team_week(client)


def test_a_52_week_year_goes_straight_to_week_1(client):
    create_plant(client)
    create_order(client, qty=500, lead_days=40, order_date=date(2027, 12, 13), name="fin de año")
    result = plan(client, 12, year=2027)["results"][0]
    # 2027 has 52 weeks: Equipo 1 wk 50, Equipo 2 wk 51, Equipo 3 wk 52, Equipo 4 wk 1 of 2028
    assert result["calculated_delivery_date"] == "2028-01-09"
    assert (3, 2027, 53) not in allocations_by_team_week(client)


def test_a_week_53_exception_is_honored(client):
    create_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=3, year=2026, week_number=53, capacity_multiplier=0))
    create_order(client, qty=500, lead_days=40, order_date=date(2026, 12, 14), name="fin de año")
    result = plan(client, 12)["results"][0]
    # Equipo 3 is closed in week 53, so it works in week 1 of 2027 and Equipo 4 follows in week 2
    assert result["calculated_delivery_date"] == "2027-01-17"
    assert (3, 2026, 53) not in allocations_by_team_week(client)
