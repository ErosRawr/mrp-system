"""The dashboard's numbers must agree with every other view of the same data."""
from datetime import date

import pytest
from helpers import create_order, create_plant, plan


def build(client):
    """Dec 2025 and Aug/Sep 2026 planned (September with plenty of late orders), October left unplanned."""
    create_plant(client)
    create_order(client, qty=1500, lead_days=40, order_date=date(2025, 12, 1), name="Dic25")
    plan(client, 12, year=2025)

    for i, lead in enumerate([40, 45, 50, 60]):
        create_order(client, qty=2500, lead_days=lead, order_date=date(2026, 8, 3), month=8, name=f"Ago{i}")
    plan(client, 8, "peps")

    for i, lead in enumerate([14, 4, 8, 3, 10, 6, 5, 40, 60]):          # seven of these cannot make it
        create_order(client, qty=3000, lead_days=lead, name=f"Sep{i}", priority=(i == 8))
    plan(client, 9, "prioritario")

    for i in range(3):
        create_order(client, qty=1000, lead_days=40, order_date=date(2026, 10, 5), month=10, name=f"Oct{i}")


def dash(client, year=2026, month=9):
    r = client.get("/dashboard", params=dict(year=year, month=month))
    assert r.status_code == 200, r.text
    return r.json()


def orders_of(client, year, month):
    return [o for o in client.get("/orders").json() if o["planning_year"] == year and o["planning_month"] == month]


def on_time_pct(orders):
    evaluated = [o for o in orders if o["lateness_status"]]
    return round(sum(o["lateness_status"] == "on_time" for o in evaluated) / len(evaluated) * 100, 1) if evaluated else None


# ---------- KPIs ----------

def test_kpis_agree_with_the_orders_list(client):
    build(client)
    orders = orders_of(client, 2026, 9)
    k = dash(client)["kpis"]
    status = [o["lateness_status"] for o in orders]
    assert k["orders"]["total"] == len(orders) == 9 and k["orders"]["unplanned"] == 0
    assert (k["on_time"]["on_time"], k["on_time"]["warning"], k["on_time"]["critical"]) == (
        status.count("on_time"), status.count("warning"), status.count("critical"))
    assert k["on_time"]["pct"] == on_time_pct(orders)
    assert k["on_time"]["warning"] + k["on_time"]["critical"] >= 7                      # the designed trouble
    assert k["tons"]["ordered"] == sum(float(o["quantity_requested"]) for o in orders)


def test_an_unplanned_month_says_so_instead_of_inventing_numbers(client):
    build(client)
    data = dash(client, month=10)
    k = data["kpis"]
    assert data["is_planned"] is False
    assert k["orders"]["total"] == 3 and k["orders"]["unplanned"] == 3 and k["orders"]["scheduled"] == 0
    assert k["on_time"]["pct"] is None and k["on_time"]["evaluated"] == 0


def test_material_totals_match_the_requirements_endpoint(client):
    build(client)
    expected = client.get("/requirements", params=dict(year=2026, month=9)).json()["totals"]
    tons = dash(client)["kpis"]["tons"]
    assert tons["raw"] == expected["raw"] and tons["overall_yield"] == expected["overall_yield"]


def test_the_comparison_month_is_the_one_before_even_across_a_year_end(client):
    build(client)
    k = dash(client)["kpis"]
    aug = orders_of(client, 2026, 8)
    assert k["orders"]["previous_total"] == len(aug) == 4
    assert k["on_time"]["previous_pct"] == on_time_pct(aug)
    assert k["tons"]["previous_ordered"] == 10000

    january = dash(client, month=1)
    assert january["previous"] == {"year": 2025, "month": 12}
    assert january["kpis"]["orders"]["previous_total"] == 1                              # the December 2025 order
    assert january["kpis"]["on_time"]["previous_pct"] == on_time_pct(orders_of(client, 2025, 12))


# ---------- occupancy ----------

def test_occupancy_is_the_same_number_the_ocupacion_tab_shows(client):
    build(client)
    teams = client.get("/teams").json()
    checked = 0
    for month in range(1, 13):
        data = dash(client, month=month)
        pcts = []
        for team, row in zip(teams, data["teams"]):
            expected = client.get(f"/teams/{team['id']}/occupancy", params=dict(year=2026, month=month)).json()
            assert row["team_name"] == team["name"]
            assert row["occupancy_pct"] == expected["overall_occupancy_pct"], (month, team["name"])
            if expected["overall_occupancy_pct"] is not None:
                pcts.append(expected["overall_occupancy_pct"])
                checked += 1
        plant = round(sum(pcts) / len(pcts), 1)
        assert data["kpis"]["occupancy"]["pct"] == plant
        series = data["months"][month - 1]["occupancy_pct"]
        assert series == (plant if sum(r["allocated"] for r in data["teams"]) > 0 else None)
    assert checked == 48


def test_the_busiest_team_is_the_bottleneck_and_an_idle_month_has_none(client):
    build(client)
    data = dash(client)
    loaded = [t for t in data["teams"] if t["allocated"] > 0]
    top = max(loaded, key=lambda t: t["occupancy_pct"])
    assert data["kpis"]["bottleneck"] == {"team_name": top["team_name"], "pct": top["occupancy_pct"]}
    assert dash(client, month=11)["kpis"]["bottleneck"] is None


def test_months_with_nothing_allocated_are_gaps_not_zero_percent(client):
    build(client)
    series = dash(client)["months"]
    assert series[7]["occupancy_pct"] is not None and series[8]["occupancy_pct"] is not None      # Aug, Sep: planned
    assert all(series[m - 1]["occupancy_pct"] is None for m in (1, 2, 3, 4, 5, 6, 11, 12))        # nothing in their weeks


# ---------- the twelve months, the attention list ----------

def test_the_year_series_has_twelve_months_with_the_right_counts(client):
    build(client)
    months = dash(client)["months"]
    assert [m["month"] for m in months] == list(range(1, 13))
    assert months[7]["orders"] == 4 and months[8]["orders"] == 9 and months[9]["orders"] == 3
    assert months[9]["unplanned"] == 3 and months[9]["planned"] is False
    assert months[7]["planned"] is True and months[8]["planned"] is True
    assert all(m["orders"] == 0 for m in months if m["month"] not in (8, 9, 10))
    for m in months:
        orders = orders_of(client, 2026, m["month"])
        assert m["on_time_pct"] == on_time_pct(orders) and m["tons"] == sum(float(o["quantity_requested"]) for o in orders)


def test_attention_lists_the_worst_late_orders_first_and_caps_the_list(client):
    build(client)
    attention = dash(client)["attention"]
    late = sorted((o for o in orders_of(client, 2026, 9) if o["lateness_status"] in ("warning", "critical")),
                  key=lambda o: (-o["days_late"], o["id"]))
    assert attention["total"] == len(late) >= 7
    assert [o["order_id"] for o in attention["orders"]] == [o["id"] for o in late][:5]
    assert len(attention["orders"]) == 5
    assert all(o["lateness_status"] in ("warning", "critical") for o in attention["orders"])
    assert dash(client, month=8)["attention"]["total"] == len([o for o in orders_of(client, 2026, 8) if o["lateness_status"] in ("warning", "critical")])


# ---------- which month it opens on, and bad input ----------

def test_it_opens_on_the_latest_planned_month(client):
    build(client)
    data = client.get("/dashboard").json()
    assert (data["year"], data["month"]) == (2026, 9) and data["is_planned"] is True


def test_with_no_plans_it_opens_on_the_latest_month_that_has_orders(client):
    create_plant(client)
    create_order(client, order_date=date(2026, 3, 2), name="a")
    create_order(client, order_date=date(2026, 7, 6), name="b")
    data = client.get("/dashboard").json()
    assert (data["year"], data["month"]) == (2026, 7) and data["is_planned"] is False


def test_an_empty_database_opens_on_today_without_failing(client):
    data = client.get("/dashboard").json()
    today = date.today()
    assert (data["year"], data["month"]) == (today.year, today.month)
    assert data["teams"] == [] and data["kpis"]["occupancy"]["pct"] is None and len(data["months"]) == 12


@pytest.mark.parametrize("params", [dict(year=2026), dict(month=9), dict(year=2026, month=13),
                                    dict(year=2026, month=0), dict(year=1500, month=1)])
def test_bad_input_is_refused(client, params):
    assert client.get("/dashboard", params=params).status_code == 400
