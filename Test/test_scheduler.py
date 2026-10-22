"""The scheduler: capacity is never exceeded, availability is respected, and failures are loud."""
import random

import models
from database import SessionLocal
from helpers import (allocations_by_team_week, by_name, calc_dates, create_order, create_plant,
                     ledger_violations, plan)


def test_fastest_possible_delivery_is_four_weeks_out(client):
    """One team per week: a Sep 1 order cannot be delivered before the end of week 39."""
    create_plant(client)
    create_order(client, qty=500, lead_days=2, name="solo")
    result = plan(client, 9)["results"][0]
    assert result["calculated_delivery_date"] == "2026-09-27"
    assert result["lateness_status"] == "critical"          # asked for Sep 3, impossible


def test_capacity_is_never_exceeded_under_heavy_load(client):
    create_plant(client)
    rng = random.Random(1)
    for i in range(25):
        create_order(client, qty=rng.choice([2500, 6000, 9000, 16000]), lead_days=rng.randint(24, 45), name=f"C{i}")
    plan(client, 9)
    assert ledger_violations(client) == []


def test_a_reduced_week_caps_the_allocation(client):
    create_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0.2))
    for i in range(6):
        create_order(client, qty=9000, lead_days=30, name=f"C{i}")
    plan(client, 9)
    assert allocations_by_team_week(client).get((4, 2026, 39), 0) <= 25000 * 0.2 + 0.01
    assert ledger_violations(client) == []


def test_a_zero_week_is_skipped_entirely(client):
    create_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0))
    create_order(client, qty=500, lead_days=30, name="solo")
    result = plan(client, 9)["results"][0]
    assert allocations_by_team_week(client).get((4, 2026, 39), 0) == 0
    assert result["calculated_delivery_date"] == "2026-10-04"      # pushed from week 39 to week 40


def test_planning_twice_gives_the_same_result(client):
    create_plant(client)
    for i in range(8):
        create_order(client, qty=5000, lead_days=30 + i, name=f"C{i}")
    plan(client, 9)
    first = calc_dates(client)
    plan(client, 9)
    assert calc_dates(client) == first
    assert ledger_violations(client) == []


def test_compare_persists_nothing(client):
    create_plant(client)
    for i in range(6):
        create_order(client, qty=5000, lead_days=30 + i, name=f"C{i}")
    plan(client, 9)
    before = (calc_dates(client), allocations_by_team_week(client))
    cmp = client.get("/planning/compare", params=dict(year=2026, month=9)).json()
    assert set(cmp["comparison"]) == {"peps", "prioritario", "heuristica"}
    assert (calc_dates(client), allocations_by_team_week(client)) == before


# ---------- failures must be loud ----------

def tiny_second_team(client):
    """Equipo 2 can do 0.01 t a month: nothing real ever fits."""
    for name, seq, cap, eff in [("Equipo 1", 1, 260000, 0.98), ("Equipo 2", 2, 0.01, 0.95),
                                ("Equipo 3", 3, 160000, 0.92), ("Equipo 4", 4, 100000, 0.96)]:
        assert client.post("/teams", params=dict(name=name, sequence_order=seq, monthly_capacity=cap, efficiency=eff)).status_code == 200


def test_an_order_that_cannot_fit_is_an_error_not_a_2051_delivery_date(client):
    tiny_second_team(client)
    create_order(client, qty=1000, lead_days=40, name="imposible")
    run = plan(client, 9)
    assert run["orders_planned"] == 0 and run["orders_failed"] == 1
    error = run["results"][0]
    assert "cannot fit" in error["error"] and "Equipo 2" in error["error"]
    assert by_name(client)["imposible"]["calculated_delivery_date"] is None


def test_a_failed_order_gives_back_everything_it_claimed(client):
    """Equipo 1 accepted the order before Equipo 2 failed: those claims must be released."""
    tiny_second_team(client)
    create_order(client, qty=1000, lead_days=40, name="imposible")
    plan(client, 9)
    assert allocations_by_team_week(client) == {}


def test_a_failed_order_does_not_hurt_the_others(client):
    create_plant(client)
    create_order(client, qty=3000, lead_days=40, name="normal")
    baseline = plan(client, 9)["results"][0]["calculated_delivery_date"]
    # now the same plant, but an impossible order sits in the same month
    db = SessionLocal()
    for week in range(1, 53):                       # Equipo 4 unavailable for six years
        for year in range(2026, 2033):
            db.add(models.TeamWeekException(team_id=4, year=year, week_number=week, capacity_multiplier=0))
    db.commit(); db.close()
    run = plan(client, 9)
    assert run["orders_failed"] == 1 and run["orders_planned"] == 0
    assert by_name(client)["normal"]["calculated_delivery_date"] is None   # stale date cleared, not kept
    assert baseline == "2026-09-27"


def test_summary_counts_failures_in_compare(client):
    tiny_second_team(client)
    create_order(client, qty=1000, lead_days=40, name="imposible")
    cmp = client.get("/planning/compare", params=dict(year=2026, month=9)).json()["comparison"]
    assert all(info["summary"]["errors"] == 1 for info in cmp.values())
