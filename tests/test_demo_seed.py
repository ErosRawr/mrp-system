"""
Locks in the demo story. If a change to the planner, the heuristics or the
seed breaks what you show in the demo, this is the test that says so.
It runs the real scripts/seed_data.py in-process against a throwaway database.
"""
import collections
import runpy
import sys
from pathlib import Path

import pytest
from tests.helpers import allocations_by_team_week, calc_dates, ledger_violations

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://localhost:8000"


class FakeRequests:
    """Stands in for the `requests` module: same calls, answered by the test client."""
    def __init__(self, client):
        self._client = client

    def post(self, url, params=None):
        return self._client.post(url.replace(BASE, ""), params=params)

    def get(self, url, params=None):
        return self._client.get(url.replace(BASE, ""), params=params)


@pytest.fixture()
def seeded(client, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "requests", FakeRequests(client))
    runpy.run_path(str(ROOT / "scripts" / "seed_data.py"))
    capsys.readouterr()
    return client


def triple(summary):
    return (summary["on_time"], summary["warning"], summary["critical"])


def test_seed_builds_the_expected_database(seeded):
    assert len(seeded.get("/teams").json()) == 4
    orders = seeded.get("/orders").json()
    assert len(orders) == 168
    assert sum(1 for o in orders if o["planning_month"] == 9) == 18
    planned = [m["planning_month"] for m in seeded.get("/planning/months").json()]
    assert planned == [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]               # September left for the demo
    assert all(o["calculated_delivery_date"] is None for o in orders if o["planning_month"] == 9)
    assert ledger_violations(seeded) == []


def test_september_comparison_tells_the_designed_story(seeded):
    cmp = seeded.get("/planning/compare", params=dict(year=2026, month=9)).json()["comparison"]
    assert triple(cmp["peps"]["summary"]) == (12, 4, 2)
    assert triple(cmp["prioritario"]["summary"]) == (14, 3, 1)
    assert triple(cmp["heuristica"]["summary"]) == (10, 5, 3)

    status = {k: {r["customer_name"]: r["lateness_status"] for r in v["results"]} for k, v in cmp.items()}
    position = {k: [r["customer_name"] for r in v["results"]] for k, v in cmp.items()}
    # Urgente Tardio: first in PEPS and on time, pushed back and critical in Heuristica
    assert position["peps"][0] == "Urgente Tardio" and status["peps"]["Urgente Tardio"] == "on_time"
    assert status["heuristica"]["Urgente Tardio"] == "critical"
    # the priority customers: late in PEPS, rescued by the other two
    for name in ("Cliente VIP", "Constructora Premium"):
        assert status["peps"][name] != "on_time"
        assert status["prioritario"][name] == "on_time" and status["heuristica"][name] == "on_time"
    assert status["peps"]["Cliente VIP"] == "critical"
    # the two big orders: late in PEPS, rescued only by Heuristica
    for name in ("Pedido Grande", "Gran Obra Federal"):
        assert status["peps"][name] != "on_time"
        assert status["heuristica"][name] == "on_time"


def test_the_rest_of_the_year_is_mostly_on_time_with_lates_scattered(seeded):
    orders = [o for o in seeded.get("/orders").json() if o["planning_month"] != 9]
    status = collections.Counter(o["lateness_status"] for o in orders)
    assert len(orders) == 150 and None not in status
    assert 0.85 <= status["on_time"] / len(orders) <= 0.95
    assert 2 <= status["critical"] <= 6 and 8 <= status["warning"] <= 18

    late_per_month = collections.Counter(o["planning_month"] for o in orders if o["lateness_status"] != "on_time")
    assert len(late_per_month) >= 6                       # scattered, not clumped in one month
    assert max(late_per_month.values()) <= 6


def test_holidays_and_productivity_drops_are_in_place(seeded):
    exceptions = seeded.get("/team-week-exceptions").json()
    holiday_rows = collections.Counter(e["team_id"] for e in exceptions if "Baja de productividad" not in (e["reason"] or "") or ";" in (e["reason"] or ""))
    assert holiday_rows[1] == 0 and holiday_rows[2] == 0               # continuous process: no reduction
    assert holiday_rows[3] == 7 and holiday_rows[4] == 7
    drops = [e for e in exceptions if "Baja de productividad" in (e["reason"] or "")]
    assert len(drops) == 21                                            # DISRUPTION_SEED = 10: 10.1% of 208 team-weeks


def test_replanning_everything_changes_nothing(seeded):
    before = (calc_dates(seeded), allocations_by_team_week(seeded))
    seeded.post("/planning/replan-all")
    assert (calc_dates(seeded), allocations_by_team_week(seeded)) == before


@pytest.mark.parametrize("criterion", ["peps", "prioritario", "heuristica"])
def test_committing_september_leaves_q4_alone(seeded, criterion):
    q4_before = {o["id"]: o["calculated_delivery_date"] for o in seeded.get("/orders").json() if o["planning_month"] >= 10}
    run = seeded.post("/planning/run", params=dict(year=2026, month=9, criterion=criterion)).json()
    assert [m["planning_month"] for m in run["replanned_months"]] == [10, 11, 12]
    q4_after = {o["id"]: o["calculated_delivery_date"] for o in seeded.get("/orders").json() if o["planning_month"] >= 10}
    assert q4_after == q4_before
    assert ledger_violations(seeded) == []
