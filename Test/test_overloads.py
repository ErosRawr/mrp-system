"""Overloads: weeks where the saved plan no longer fits the availability."""
import random
from datetime import date

import pytest
from helpers import create_order, create_plant, ledger_violations, plan


def planned_plant(client):
    create_plant(client)
    rng = random.Random(2)
    for i in range(14):
        create_order(client, qty=rng.choice([4000, 9000, 15000]), lead_days=rng.randint(24, 40), name=f"C{i}")
    plan(client, 9)


def overloads(client, **params):
    r = client.get("/availability/overloads", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_fresh_plan_has_no_overloads(client):
    planned_plant(client)
    assert overloads(client) == []


def test_cutting_capacity_after_planning_creates_an_overload_with_the_right_numbers(client):
    planned_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0.2))
    rows = overloads(client)
    assert rows, "the plan used Equipo 4 in week 39, so cutting it must overload that week"
    week39 = next(r for r in rows if r["team_id"] == 4 and r["week_number"] == 39)
    assert week39["capacity"] == pytest.approx(25000 * 0.2, abs=0.01)                      # 5,000 t left
    assert week39["allocated"] > week39["capacity"]
    assert week39["excess"] == pytest.approx(week39["allocated"] - week39["capacity"], abs=0.011)
    assert week39["team_name"] == "Equipo 4" and week39["year"] == 2026


def test_it_is_the_same_rule_as_the_ledger_check_the_tests_already_use(client):
    planned_plant(client)
    for team, week, mult in [(4, 39, 0.2), (3, 38, 0.0), (2, 37, 0.5)]:
        client.post("/team-week-exceptions", params=dict(team_id=team, year=2026, week_number=week, capacity_multiplier=mult))
    expected = {(v[0], v[1], v[2]) for v in ledger_violations(client)}
    got = {(r["team_name"], r["year"], r["week_number"]) for r in overloads(client)}
    assert got == expected and len(got) >= 2


def test_a_closed_week_that_still_holds_work_is_an_overload_with_zero_capacity(client):
    planned_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0))
    week39 = next(r for r in overloads(client) if r["team_id"] == 4 and r["week_number"] == 39)
    assert week39["capacity"] == 0 and week39["excess"] == week39["allocated"]


def test_replanning_clears_the_overloads(client):
    planned_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0.2))
    assert overloads(client)
    client.post("/planning/replan-all")
    assert overloads(client) == []


def test_a_week_that_is_exactly_full_is_not_an_overload(client):
    create_plant(client)
    create_order(client, qty=25000, team_id=4, lead_days=60, name="justo")       # fills Equipo 4's week exactly
    plan(client, 9)
    assert overloads(client) == []


def test_the_year_filter_and_ordering(client):
    planned_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=39, capacity_multiplier=0.2))
    client.post("/team-week-exceptions", params=dict(team_id=2, year=2026, week_number=37, capacity_multiplier=0.1))
    assert overloads(client, year=2027) == []
    rows = overloads(client, year=2026)
    assert [(r["year"], r["week_number"]) for r in rows] == sorted((r["year"], r["week_number"]) for r in rows)


def test_bad_year_is_refused(client):
    assert client.get("/availability/overloads", params=dict(year=1500)).status_code == 400
