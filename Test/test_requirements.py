"""Material requirements: per order (with losses) and rolled up for a month."""
from datetime import date

import pytest
from helpers import create_order, create_plant


def requirements(client, order_id):
    return client.get(f"/orders/{order_id}/requirements").json()


def monthly(client, month=9, year=2026):
    return client.get("/requirements", params=dict(year=year, month=month))


# ---------- one order ----------

def test_the_worked_example_now_reports_its_losses(client):
    """100 t through .96 .92 .95 .98: 121.62 t in, 21.62 t scrapped, 82.2% yield."""
    create_plant(client)
    data = requirements(client, create_order(client, qty=100, team_id=4)["id"])
    assert data["total_raw_material_needed"] == 121.62
    assert data["total_loss"] == 21.62
    assert data["overall_yield"] == pytest.approx(100 / 121.62, abs=1e-4)
    assert data["error"] is None
    # each team's loss is its input minus its output, and they add up to the total
    assert [s["loss"] for s in data["steps"]] == [4.17, 9.06, 5.96, 2.43]     # Equipo 4, 3, 2, 1
    assert sum(s["loss"] for s in data["steps"]) == pytest.approx(data["total_loss"], abs=0.02)
    for s in data["steps"]:
        assert s["loss"] == pytest.approx(s["input_needed"] - s["output_needed"], abs=0.011)


def test_an_order_entering_midway_only_counts_the_teams_it_passes_through(client):
    create_plant(client)
    data = requirements(client, create_order(client, qty=100, team_id=2)["id"])
    assert [s["team_name"] for s in data["steps"]] == ["Equipo 2", "Equipo 1"]
    assert data["total_loss"] == pytest.approx(data["total_raw_material_needed"] - 100, abs=0.011)


# ---------- the month ----------

def build_month(client):
    create_plant(client)
    a = create_order(client, qty=100, team_id=4, name="A")["id"]
    b = create_order(client, qty=20000, team_id=4, name="B")["id"]
    c = create_order(client, qty=5000, team_id=2, name="C")["id"]
    create_order(client, qty=777, team_id=4, name="Octubre", month=10, order_date=date(2026, 9, 14))
    return a, b, c


def test_month_totals_are_the_sum_of_the_orders(client):
    a, b, c = build_month(client)
    data = monthly(client).json()
    assert data["orders_count"] == 3                                # the October order is not in September
    assert [o["customer_name"] for o in data["orders"]] == ["A", "B", "C"]
    assert data["totals"]["finished"] == 25100
    per_order_raw = sum(requirements(client, i)["total_raw_material_needed"] for i in (a, b, c))
    assert data["totals"]["raw"] == pytest.approx(per_order_raw, abs=0.02)
    assert data["totals"]["loss"] == pytest.approx(data["totals"]["raw"] - 25100, abs=0.011)
    assert data["totals"]["overall_yield"] == pytest.approx(25100 / data["totals"]["raw"], abs=1e-4)
    assert data["errors"] == []


def test_each_team_adds_up_only_the_orders_that_pass_through_it(client):
    build_month(client)
    teams = {t["team_name"]: t for t in monthly(client).json()["teams"]}
    assert [t for t in teams] == ["Equipo 1", "Equipo 2", "Equipo 3", "Equipo 4"]
    assert teams["Equipo 4"]["orders"] == 2 and teams["Equipo 4"]["output_needed"] == 20100   # A + B, C never reaches it
    assert teams["Equipo 2"]["orders"] == 3 and teams["Equipo 1"]["orders"] == 3
    assert teams["Equipo 4"]["load_pct"] == 20.1                                              # 20,100 t of 100,000 t
    assert teams["Equipo 1"]["input_needed"] == pytest.approx(monthly(client).json()["totals"]["raw"], abs=0.02)
    for t in teams.values():
        assert t["loss"] == pytest.approx(t["input_needed"] - t["output_needed"], abs=0.011)


def test_a_team_asked_for_more_than_its_capacity_shows_over_100_percent(client):
    create_plant(client)
    create_order(client, qty=120000, team_id=4, name="Gigante")
    team4 = [t for t in monthly(client).json()["teams"] if t["team_name"] == "Equipo 4"][0]
    assert team4["load_pct"] == 120.0


def test_an_empty_month_is_an_empty_answer_not_an_error(client):
    create_plant(client)
    r = monthly(client, month=11)
    assert r.status_code == 200
    data = r.json()
    assert data["orders_count"] == 0 and data["orders"] == [] and data["totals"]["raw"] == 0
    assert data["totals"]["overall_yield"] is None
    assert all(t["orders"] == 0 and t["load_pct"] == 0 for t in data["teams"])


def test_bad_months_are_refused(client):
    create_plant(client)
    assert monthly(client, month=13).status_code == 400
    assert monthly(client, month=0).status_code == 400
    assert monthly(client, year=1500).status_code == 400
