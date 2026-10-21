"""Bad input must be refused with a clear 400, and must never be stored."""
from datetime import date

import pytest
from tests.helpers import create_order, create_plant

GOOD_TEAM = dict(name="Equipo X", sequence_order=9, monthly_capacity=1000, efficiency=0.9)

BAD_TEAMS = {
    "blank name": dict(name=""),
    "whitespace name": dict(name="   "),
    "markup in name": dict(name="<b>x</b>"),
    "name too long": dict(name="x" * 101),
    "sequence 0": dict(sequence_order=0),
    "negative sequence": dict(sequence_order=-1),
    "zero capacity": dict(monthly_capacity=0),
    "nan capacity": dict(monthly_capacity="nan"),
    "inf capacity": dict(monthly_capacity="inf"),
    "absurd capacity": dict(monthly_capacity=10**12),
    "zero efficiency": dict(efficiency=0),
    "efficiency above 1": dict(efficiency=1.5),
    "nan efficiency": dict(efficiency="nan"),
    "zero weeks": dict(weeks_available=0),
    "six weeks": dict(weeks_available=6),
    "staffing above 1": dict(holiday_staffing=1.5),
    "nan staffing": dict(holiday_staffing="nan"),
}


@pytest.mark.parametrize("override", BAD_TEAMS.values(), ids=BAD_TEAMS.keys())
def test_bad_team_is_refused_and_not_stored(client, override):
    r = client.post("/teams", params={**GOOD_TEAM, **override})
    assert r.status_code == 400, r.text
    assert client.get("/teams").json() == []          # nothing stored, and /teams still works


def test_duplicate_team_name_and_sequence_are_refused(client):
    assert client.post("/teams", params=GOOD_TEAM).status_code == 200
    same_name = client.post("/teams", params={**GOOD_TEAM, "name": "equipo x", "sequence_order": 11})
    assert same_name.status_code == 400 and "already exists" in same_name.text
    same_seq = client.post("/teams", params={**GOOD_TEAM, "name": "Otro", "sequence_order": 9})
    assert same_seq.status_code == 400


def test_team_name_is_trimmed(client):
    r = client.post("/teams", params={**GOOD_TEAM, "name": "  Laminacion  "})
    assert r.json()["name"] == "Laminacion"


BAD_ORDERS = {
    "blank customer": dict(customer_name="  "),
    "markup in customer": dict(customer_name="<img src=x onerror=alert(1)>"),
    "customer too long": dict(customer_name="x" * 101),
    "control character": dict(customer_name="a\x00b"),
    "zero tons": dict(quantity_requested=0),
    "negative tons": dict(quantity_requested=-5),
    "nan tons": dict(quantity_requested="nan"),
    "inf tons": dict(quantity_requested="inf"),
    "absurd tons": dict(quantity_requested=1e30),
    "tons above the single-order limit": dict(quantity_requested=1_000_001),
    "month 0": dict(planning_month=0),
    "month 13": dict(planning_month=13),
    "year 1900": dict(planning_year=1900),
    "negative year": dict(planning_year=-5),
    "order date in year 1500": dict(order_date="1500-01-01"),
    "requested before ordered": dict(requested_delivery_date="2026-02-01"),
    "unknown entry team": dict(entry_team_id=999),
    "markup in tipo": dict(tipo_pedido="<x>"),
}


@pytest.mark.parametrize("override", BAD_ORDERS.values(), ids=BAD_ORDERS.keys())
def test_bad_order_is_refused_and_not_stored(client, override):
    create_plant(client)
    good = dict(customer_name="A", quantity_requested=1000, entry_team_id=4, order_date="2026-03-02")
    assert client.post("/orders", params={**good, **override}).status_code == 400
    assert client.get("/orders").json() == []


def test_blank_tipo_is_stored_as_none_and_text_is_trimmed(client):
    create_plant(client)
    r = client.post("/orders", params=dict(customer_name="  Aceros  ", quantity_requested=10, entry_team_id=4,
                                           order_date="2026-03-02", tipo_pedido="   "))
    assert r.status_code == 200
    assert r.json()["customer_name"] == "Aceros" and r.json()["tipo_pedido"] is None


@pytest.mark.parametrize("override", [dict(planning_month=13), dict(planning_year=1900), dict(customer_name=" "),
                                      dict(quantity_requested="nan"), dict(customer_name="<script>")])
def test_bad_update_is_refused_and_changes_nothing(client, override):
    create_plant(client)
    order = create_order(client, qty=1000, name="Original")
    assert client.put(f"/orders/{order['id']}", params=override).status_code == 400
    after = client.get("/orders").json()[0]
    assert after["customer_name"] == "Original" and after["planning_month"] == 9 and after["quantity_requested"] == 1000


def test_exception_validation(client):
    create_plant(client)
    base = dict(team_id=1, year=2026, week_number=5, capacity_multiplier=0.5)
    assert client.post("/team-week-exceptions", params=base).status_code == 200
    for override in (dict(year=1800), dict(week_number=0), dict(week_number=54),
                     dict(year=2027, week_number=53),            # 2027 only has 52 ISO weeks
                     dict(capacity_multiplier="nan"), dict(capacity_multiplier=1.5), dict(reason="<b>")):
        r = client.post("/team-week-exceptions", params={**base, **override, "week_number": override.get("week_number", 6)})
        assert r.status_code == 400, (override, r.text)
    # week 53 exists in 2026 (a 53-week ISO year), so it is accepted
    assert client.post("/team-week-exceptions", params={**base, "week_number": 53}).status_code == 200


def test_planning_inputs(client):
    create_plant(client)
    create_order(client, month=3, order_date=date(2026, 3, 2))
    for params in (dict(year=-5, month=1), dict(year=2026, month=13), dict(year=2026, month=0),
                   dict(year=2026, month=3, criterion="nope")):
        assert client.post("/planning/run", params=params).status_code == 400, params
    assert client.get("/planning/compare", params=dict(year=-5, month=1)).status_code == 400
    assert client.get("/planning/compare", params=dict(year=2026, month=13)).status_code == 400
    # a month with no orders is refused and leaves no phantom "planned month" behind
    r = client.post("/planning/run", params=dict(year=2026, month=11))
    assert r.status_code == 400 and "nothing to plan" in r.text
    assert client.get("/planning/months").json() == []


def test_missing_things_are_404_not_200(client):
    create_plant(client)
    assert client.get("/orders/999/requirements").status_code == 404
    assert client.put("/orders/999", params=dict(customer_name="x")).status_code == 404
    assert client.delete("/orders/999").status_code == 404
    assert client.get("/teams/999/occupancy", params=dict(year=2026, month=3)).status_code == 404


def test_occupancy_rejects_impossible_dates(client):
    create_plant(client)
    assert client.get("/teams/1/occupancy", params=dict(year=2026, month=13)).status_code == 400
    assert client.get("/teams/1/occupancy", params=dict(year=1500, month=1)).status_code == 400


def test_disruption_and_holiday_inputs(client):
    create_plant(client)
    for params in (dict(year=2026, probability=1.5), dict(year=2026, probability="nan"),
                   dict(year=2026, min_drop=0.5, max_drop=0.2), dict(year=1800), dict(year=2026, min_drop=0)):
        assert client.post("/team-week-exceptions/generate-disruptions", params=params).status_code == 400, params
    assert client.post("/team-week-exceptions/generate-disruptions", params=dict(year=2026, team_id=99)).status_code == 404
    for days in (0, 8):
        r = client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=1, year=2026, working_days_per_week=days))
        assert r.status_code == 400


def test_app_still_works_after_every_kind_of_bad_input(client):
    """Regression: a stored nan used to make GET /teams return 500 permanently."""
    for value in ("nan", "inf"):
        client.post("/teams", params={**GOOD_TEAM, "monthly_capacity": value})
    assert client.get("/teams").status_code == 200
    assert client.get("/orders").status_code == 200
