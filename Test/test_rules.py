"""The business rules: material requirements, lateness, and the three sort criteria."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from helpers import create_order, create_plant

from heuristics import sort_orders_heuristica, sort_orders_peps, sort_orders_prioritario
from lateness import classify_lateness


# ---------- material requirements ----------

def test_worked_example_100_tons_needs_121_62_raw(client):
    """The professor's example: efficiencies .98 .95 .92 .96 turn 100 t into 121.62 t of raw input."""
    create_plant(client)
    order = create_order(client, qty=100, team_id=4)
    data = client.get(f"/orders/{order['id']}/requirements").json()
    assert data["total_raw_material_needed"] == 121.62
    assert [s["team_name"] for s in data["steps"]] == ["Equipo 4", "Equipo 3", "Equipo 2", "Equipo 1"]
    assert data["steps"][0]["output_needed"] == 100


def test_an_order_only_needs_the_teams_up_to_its_entry_point(client):
    create_plant(client)
    order = create_order(client, qty=100, team_id=2)
    steps = client.get(f"/orders/{order['id']}/requirements").json()["steps"]
    assert [s["team_name"] for s in steps] == ["Equipo 2", "Equipo 1"]


# ---------- lateness ----------

@pytest.mark.parametrize("days_late, expected", [
    (-30, "on_time"), (0, "on_time"), (7, "on_time"),
    (8, "warning"), (14, "warning"),
    (15, "critical"), (90, "critical"),
])
def test_lateness_boundaries(days_late, expected):
    requested = date(2026, 9, 10)
    status = classify_lateness(requested + timedelta(days=days_late), requested)[1]
    assert status == expected


def test_lateness_is_none_without_both_dates():
    d = date(2026, 9, 10)
    assert classify_lateness(None, d) == (None, None, None)
    assert classify_lateness(d, None) == (None, None, None)


def test_only_days_beyond_the_grace_count_as_late():
    assert classify_lateness(date(2026, 9, 17), date(2026, 9, 10))[2] is False   # 7 days: inside the grace
    assert classify_lateness(date(2026, 9, 18), date(2026, 9, 10))[2] is True    # 8 days


# ---------- sort criteria ----------

def fake(id, requested, qty=1000, priority=False, tipo=None):
    return SimpleNamespace(id=id, requested_delivery_date=requested, order_date=date(2026, 9, 1),
                           quantity_requested=qty, is_priority=priority, tipo_pedido=tipo)


def ids(orders):
    return [o.id for o in orders]


def test_peps_orders_by_requested_date_and_puts_missing_dates_last():
    orders = [fake(1, date(2026, 10, 5)), fake(2, None), fake(3, date(2026, 10, 1)), fake(4, date(2026, 10, 1))]
    assert ids(sort_orders_peps(orders)) == [3, 4, 1, 2]       # ties broken by id


def test_prioritario_puts_priority_first_then_by_date():
    orders = [fake(1, date(2026, 10, 1)), fake(2, date(2026, 10, 9), priority=True), fake(3, date(2026, 10, 3), priority=True)]
    assert ids(sort_orders_prioritario(orders)) == [3, 2, 1]


def test_heuristica_priority_then_big_tonnage_then_tipo_then_date():
    orders = [
        fake(1, date(2026, 10, 1), qty=3000, tipo="especial"),
        fake(2, date(2026, 10, 9), qty=3000, tipo="comercial"),
        fake(3, date(2026, 10, 9), qty=18000, tipo="tuberia"),
        fake(4, date(2026, 10, 9), qty=16000, tipo="tuberia"),
        fake(5, date(2026, 10, 20), qty=3000, tipo="comercial", priority=True),
    ]
    # priority first; then 15k+ biggest first; then the rest by tipo rank (comercial before especial)
    assert ids(sort_orders_heuristica(orders)) == [5, 3, 4, 2, 1]


def test_heuristica_below_the_threshold_tonnage_does_not_matter():
    orders = [fake(1, date(2026, 10, 1), qty=14999, tipo="comercial"), fake(2, date(2026, 10, 1), qty=100, tipo="comercial")]
    assert ids(sort_orders_heuristica(orders)) == [1, 2]       # tie on tonnage tier -> falls through to date, then id


def test_unknown_or_missing_tipo_sorts_last():
    orders = [fake(1, date(2026, 10, 1), tipo=None), fake(2, date(2026, 10, 1), tipo="raro"), fake(3, date(2026, 10, 1), tipo="especial")]
    assert ids(sort_orders_heuristica(orders))[0] == 3
