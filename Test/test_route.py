"""The route summary: what the plant can really produce, from the teams' configuration alone."""
import pytest
from helpers import create_order, create_plant


def route(client):
    r = client.get("/route")
    assert r.status_code == 200, r.text
    return r.json()


def team(data, name):
    return next(t for t in data["teams"] if t["team_name"] == name)


def test_the_demo_plant_is_limited_by_equipo_4_at_25000_finished_tons_a_week(client):
    create_plant(client)                      # .98 .95 .92 .96 and 65,000 / 50,000 / 40,000 / 25,000 t a week
    data = route(client)
    assert data["bottleneck"]["team_name"] == "Equipo 4"
    assert data["finished_capacity_week"] == 25000 and data["finished_capacity_month"] == 100000
    assert [t["team_name"] for t in data["teams"]] == ["Equipo 1", "Equipo 2", "Equipo 3", "Equipo 4"]
    # what each team could support in FINISHED tons: its weekly capacity discounted by every team after it
    assert team(data, "Equipo 4")["finished_capacity_week"] == 25000
    assert team(data, "Equipo 3")["finished_capacity_week"] == pytest.approx(40000 * 0.96, abs=0.01)
    assert team(data, "Equipo 2")["finished_capacity_week"] == pytest.approx(50000 * 0.92 * 0.96, abs=0.01)
    assert team(data, "Equipo 1")["finished_capacity_week"] == pytest.approx(65000 * 0.95 * 0.92 * 0.96, abs=0.01)


def test_the_load_of_each_team_when_the_bottleneck_runs_flat_out(client):
    create_plant(client)
    data = route(client)
    assert team(data, "Equipo 4")["load_at_full_rate_pct"] == 100 and team(data, "Equipo 4")["is_bottleneck"] is True
    assert [team(data, f"Equipo {i}")["load_at_full_rate_pct"] for i in (1, 2, 3)] == [45.8, 56.6, 65.1]
    assert sum(t["is_bottleneck"] for t in data["teams"]) == 1
    assert all(0 < t["load_at_full_rate_pct"] <= 100 for t in data["teams"])


def test_yield_and_raw_material_agree_with_the_requirements_calculation(client):
    create_plant(client)
    data = route(client)
    assert data["overall_yield"] == pytest.approx(0.98 * 0.95 * 0.92 * 0.96, abs=1e-4)
    order = create_order(client, qty=100, team_id=4)
    assert client.get(f"/orders/{order['id']}/requirements").json()["total_raw_material_needed"] == data["raw_per_100_t"] == 121.62


def test_the_bottleneck_moves_when_another_team_becomes_the_scarce_one(client):
    for name, seq, capacity in [("A", 1, 260000), ("B", 2, 30000), ("C", 3, 160000), ("D", 4, 100000)]:
        assert client.post("/teams", params=dict(name=name, sequence_order=seq, monthly_capacity=capacity, efficiency=0.9)).status_code == 200
    data = route(client)
    assert data["bottleneck"]["team_name"] == "B"
    assert data["finished_capacity_week"] == pytest.approx(30000 / 4 * 0.9 * 0.9, abs=0.01)     # C and D come after B
    assert team(data, "B")["load_at_full_rate_pct"] == 100


def test_a_single_team_route(client):
    client.post("/teams", params=dict(name="Solo", sequence_order=1, monthly_capacity=8000, efficiency=0.8))
    data = route(client)
    assert data["bottleneck"]["team_name"] == "Solo" and data["finished_capacity_week"] == 2000
    assert data["overall_yield"] == 0.8 and data["raw_per_100_t"] == 125


def test_no_teams_is_an_empty_answer_not_an_error(client):
    data = route(client)
    assert data["teams"] == [] and data["bottleneck"] is None and data["overall_yield"] is None
