"""Months are planned in calendar order: earlier months always get first claim on capacity."""
import random
from datetime import date

import pytest
from tests.helpers import (allocations_by_team_week, calc_dates, create_order, create_plant, ledger_violations,
                     plan, reset_database)

CRITERION = {8: "peps", 9: "prioritario", 10: "heuristica"}


def build(client):
    """Three overlapping monthly batches (the October batch deliberately reuses September's weeks)."""
    create_plant(client)
    rng = random.Random(3)
    for month, order_date in ((8, date(2026, 8, 24)), (9, date(2026, 9, 1)), (10, date(2026, 9, 14))):
        for i in range(12):
            create_order(client, qty=rng.choice([2500, 4000, 6000, 9000, 15500]),
                         lead_days=rng.randint(24, 40), order_date=order_date, month=month,
                         name=f"M{month}-{i}", priority=rng.random() < 0.15,
                         tipo=rng.choice(["comercial", "especial", "tuberia"]))


def state(client):
    return calc_dates(client), allocations_by_team_week(client)


@pytest.fixture()
def chronological(client):
    build(client)
    for month in (8, 9, 10):
        plan(client, month, CRITERION[month])
    return client, state(client)


@pytest.mark.parametrize("order", [(10, 9, 8), (9, 10, 8), (10, 8, 9)])
def test_planning_in_any_order_ends_in_the_same_place(chronological, order):
    _, expected = chronological
    client, _ = chronological
    reset_database()                               # same data again, planned in a different order
    build(client)
    for month in order:
        plan(client, month, CRITERION[month])
    assert state(client) == expected


def test_committing_a_month_replans_the_later_ones_with_their_own_criterion(client):
    build(client)
    plan(client, 8, "peps"); plan(client, 10, "heuristica")
    run = plan(client, 9, "prioritario")
    assert [(m["planning_month"], m["criterion"]) for m in run["replanned_months"]] == [(10, "heuristica")]
    assert client.get("/planning/months").json() == [
        {"planning_year": 2026, "planning_month": m, "criterion": CRITERION[m]} for m in (8, 9, 10)]


def test_replanning_an_earlier_month_replans_the_later_ones(client):
    build(client)
    plan(client, 10, "heuristica"); plan(client, 9, "prioritario")
    run = plan(client, 8, "peps")
    assert [m["planning_month"] for m in run["replanned_months"]] == [9, 10]


def test_compare_ignores_later_months_and_persists_nothing(client):
    build(client)
    plan(client, 8, "peps"); plan(client, 10, "heuristica")
    before = state(client)
    with_october = client.get("/planning/compare", params=dict(year=2026, month=9)).json()
    assert state(client) == before
    assert [m["planning_month"] for m in with_october["later_planned_months"]] == [10]

    # same data, but October never planned: the September comparison must be identical
    reset_database()
    build(client)
    plan(client, 8, "peps")
    without_october = client.get("/planning/compare", params=dict(year=2026, month=9)).json()

    def shape(cmp):
        return {k: [(r["customer_name"], r["calculated_delivery_date"], r["lateness_status"]) for r in v["results"]]
                for k, v in cmp["comparison"].items()}
    assert shape(with_october) == shape(without_october)


def test_replan_all_changes_nothing_when_plans_are_current(chronological):
    client, expected = chronological
    months = client.post("/planning/replan-all").json()["months_replanned"]
    assert [m["planning_month"] for m in months] == [8, 9, 10]
    assert state(client) == expected


def test_plans_go_stale_after_an_availability_change_until_replanned(chronological):
    client, expected = chronological
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0.2))
    assert state(client) == expected                       # nothing moves on its own...
    client.post("/planning/replan-all")
    assert state(client) != expected                       # ...until you re-plan
    assert allocations_by_team_week(client).get((4, 2026, 39), 0) <= 25000 * 0.2 + 0.01
    assert ledger_violations(client) == []


def test_replan_all_with_nothing_planned_is_harmless(client):
    create_plant(client)
    assert client.post("/planning/replan-all").json() == {"months_replanned": []}
