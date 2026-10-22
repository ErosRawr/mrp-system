"""Manual planning: the hand-made sequence is the plan, preview is free, Hold is excluded."""
from datetime import date

from helpers import (allocations_by_team_week, by_name, calc_dates, create_order, create_plant,
                     ledger_violations, plan)


def three_orders(client):
    """PEPS order is A, C, B. A and B are big enough to fight over Equipo 4."""
    create_plant(client)
    a = create_order(client, qty=20000, lead_days=30, name="A")
    c = create_order(client, qty=3000, lead_days=45, name="C")
    b = create_order(client, qty=20000, lead_days=60, name="B")
    return a["id"], b["id"], c["id"]


def manual(client, order_ids, hold_ids=(), action="run-manual", month=9):
    return client.post(f"/planning/{action}", json=dict(
        year=2026, month=month, order_ids=list(order_ids), hold_ids=list(hold_ids)))


def state(client):
    return calc_dates(client), allocations_by_team_week(client)


def test_the_saved_sequence_is_the_plan(client):
    a, b, c = three_orders(client)
    assert manual(client, [b, c, a]).status_code == 200
    d = by_name(client)
    assert d["B"]["calculated_delivery_date"] < d["A"]["calculated_delivery_date"]

    manual(client, [a, c, b])
    d = by_name(client)
    assert d["A"]["calculated_delivery_date"] < d["B"]["calculated_delivery_date"]
    assert ledger_violations(client) == []
    assert client.get("/planning/months").json() == [
        {"planning_year": 2026, "planning_month": 9, "criterion": "manual"}]


def test_preview_persists_nothing(client):
    a, b, c = three_orders(client)
    plan(client, 9, "peps")
    before = state(client)
    r = manual(client, [b, c, a], action="preview-manual")
    assert r.status_code == 200 and len(r.json()["results"]) == 3
    assert state(client) == before
    assert client.get("/planning/months").json()[0]["criterion"] == "peps"


def test_preview_is_exactly_what_save_produces(client):
    a, b, c = three_orders(client)
    preview = manual(client, [b, c, a], [], action="preview-manual").json()
    saved = manual(client, [b, c, a]).json()

    def dates(payload):
        return {r["order_id"]: r["calculated_delivery_date"] for r in payload["results"]}
    assert dates(preview) == dates(saved)
    assert {"on_time", "warning", "critical", "bottleneck"} <= set(preview["summary"])
    # Equipo 3 is completely full in its busiest week (40,000 of 40,000 t); Equipo 4 peaks at 92%.
    assert preview["summary"]["bottleneck"] == "Equipo 3"


def test_held_orders_are_not_planned_and_hold_nothing(client):
    a, b, c = three_orders(client)
    r = manual(client, [a, c], [b]).json()
    assert r["orders_planned"] == 2 and r["held_order_ids"] == [b]
    assert by_name(client)["B"]["calculated_delivery_date"] is None
    for team in client.get("/teams").json():
        claimed = client.get(f"/teams/{team['id']}/capacity-allocations").json()
        assert all(row["order_id"] != b for row in claimed)

    # take it off Hold: it gets planned; put it back: its stale date is cleared
    manual(client, [a, b, c])
    assert by_name(client)["B"]["calculated_delivery_date"] is not None
    manual(client, [a, c], [b])
    assert by_name(client)["B"]["calculated_delivery_date"] is None
    assert ledger_violations(client) == []


def test_a_request_that_does_not_match_the_month_is_refused_and_stores_nothing(client):
    a, b, c = three_orders(client)
    october = create_order(client, qty=1000, name="Oct", month=10, order_date=date(2026, 9, 14))["id"]
    bad_bodies = {
        "duplicate": ([a, a, b, c], []),
        "in both lists": ([a, b, c], [a]),
        "unknown id": ([a, b, c, 999], []),
        "missing order": ([a, b], []),
        "another month's order": ([a, b, c, october], []),
    }
    for label, (order_ids, hold_ids) in bad_bodies.items():
        for action in ("preview-manual", "run-manual"):
            assert manual(client, order_ids, hold_ids, action=action).status_code == 400, (label, action)
    assert client.get("/planning/months").json() == []
    assert all(v is None for v in calc_dates(client).values())


def test_a_manual_month_keeps_its_sequence_when_an_earlier_month_is_replanned(client):
    create_plant(client)
    create_order(client, qty=15000, lead_days=30, name="Aug", month=8, order_date=date(2026, 8, 3))
    a = create_order(client, qty=20000, lead_days=30, name="A")["id"]
    b = create_order(client, qty=20000, lead_days=60, name="B")["id"]
    manual(client, [b, a])                                  # B before A, against PEPS

    run = plan(client, 8, "peps")
    assert [(m["planning_month"], m["criterion"]) for m in run["replanned_months"]] == [(9, "manual")]
    d = by_name(client)
    assert d["B"]["calculated_delivery_date"] < d["A"]["calculated_delivery_date"]

    before = state(client)
    client.post("/planning/replan-all")
    assert state(client) == before


def test_orders_added_after_saving_are_planned_at_the_end(client):
    a, b, c = three_orders(client)
    manual(client, [b, c, a])
    create_order(client, qty=2000, lead_days=50, name="Late")
    client.post("/planning/replan-all")
    d = by_name(client)
    assert d["Late"]["calculated_delivery_date"] is not None
    assert d["B"]["calculated_delivery_date"] < d["A"]["calculated_delivery_date"]
    assert ledger_violations(client) == []


def test_committing_an_automatic_criterion_replaces_the_manual_plan(client):
    a, b, c = three_orders(client)
    plan(client, 9, "peps")
    peps = calc_dates(client)

    manual(client, [b, c, a])
    assert calc_dates(client) != peps

    plan(client, 9, "peps")
    assert calc_dates(client) == peps
    client.post("/planning/replan-all")                     # the old manual sequence must be gone
    assert calc_dates(client) == peps
    assert client.get("/planning/months").json()[0]["criterion"] == "peps"


def test_deleting_an_order_in_a_manual_month_does_not_break_replanning(client):
    a, b, c = three_orders(client)
    manual(client, [a, b, c])
    assert client.delete(f"/orders/{b}").status_code == 200
    months = client.post("/planning/replan-all").json()["months_replanned"]
    assert months[0]["orders_failed"] == 0 and months[0]["orders_planned"] == 2
    assert ledger_violations(client) == []
