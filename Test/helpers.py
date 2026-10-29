"""Small factories shared by the tests."""
from datetime import date, timedelta

import models
from database import engine


def reset_database():
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)

# The demo plant: 4 teams in a row, Equipo 4 is the bottleneck (25,000 t/week).
PLANT = [
    ("Equipo 1", 1, 260000, 0.98),
    ("Equipo 2", 2, 200000, 0.95),
    ("Equipo 3", 3, 160000, 0.92),
    ("Equipo 4", 4, 100000, 0.96),
]


def create_plant(client, staffing=(0, 0, 0, 0)):
    ids = []
    for (name, seq, capacity, efficiency), share in zip(PLANT, staffing):
        r = client.post("/teams", params=dict(name=name, sequence_order=seq, monthly_capacity=capacity,
                                              efficiency=efficiency, holiday_staffing=share))
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    return ids


def create_order(client, qty=1000, lead_days=40, order_date=date(2026, 9, 1), month=None, team_id=4,
                 name="Cliente", priority=False, tipo=None, expect=200):
    params = dict(customer_name=name, quantity_requested=qty, entry_team_id=team_id,
                  order_date=order_date.isoformat(),
                  requested_delivery_date=(order_date + timedelta(days=lead_days)).isoformat(),
                  is_priority=priority)
    if month is not None:
        params["planning_month"] = month
        params["planning_year"] = order_date.year
    if tipo:
        params["tipo_pedido"] = tipo
    r = client.post("/orders", params=params)
    assert r.status_code == expect, r.text
    return r.json()


def plan(client, month, criterion="peps", year=2026):
    r = client.post("/planning/run", params=dict(year=year, month=month, criterion=criterion))
    assert r.status_code == 200, r.text
    return r.json()


def by_name(client):
    return {o["customer_name"]: o for o in client.get("/orders").json()}


def calc_dates(client):
    return {o["id"]: o["calculated_delivery_date"] for o in client.get("/orders").json()}


def allocations_by_team_week(client):
    """{(team_id, year, week): tons} from the capacity ledger."""
    totals = {}
    for team in client.get("/teams").json():
        for a in client.get(f"/teams/{team['id']}/capacity-allocations").json():
            key = (team["id"], a["year"], a["week_number"])
            totals[key] = totals.get(key, 0) + float(a["quantity_allocated"])
    return totals


def ledger_violations(client):
    """Weeks where a team was given more work than its effective capacity."""
    teams = {t["id"]: t for t in client.get("/teams").json()}
    multiplier = {(e["team_id"], e["year"], e["week_number"]): float(e["capacity_multiplier"])
                  for e in client.get("/team-week-exceptions").json()}
    bad = []
    for (team_id, year, week), used in allocations_by_team_week(client).items():
        cap = teams[team_id]["weekly_capacity"] * multiplier.get((team_id, year, week), 1.0)
        if used > cap + 0.01:
            bad.append((teams[team_id]["name"], year, week, round(used), round(cap)))
    return bad
