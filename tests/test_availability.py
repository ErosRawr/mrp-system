"""Holidays (per-team staffing) and random productivity drops."""
import statistics

import pytest
from tests.helpers import create_plant

from disruptions import draw_disruptions

WEEK_38 = 38     # Independence Day, Wednesday 2026-09-16


def week_multiplier(client, team_id, week):
    rows = [e for e in client.get("/team-week-exceptions").json() if e["team_id"] == team_id and e["week_number"] == week]
    return float(rows[0]["capacity_multiplier"]) if rows else None


# ---------- holidays ----------

@pytest.mark.parametrize("staffing, expected", [(0.0, 0.8), (0.5, 0.9), (1.0, None)])
def test_holiday_cost_depends_on_team_staffing(client, staffing, expected):
    create_plant(client, staffing=(staffing, 0, 0, 0))
    client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=1, year=2026))
    assert week_multiplier(client, 1, WEEK_38) == (pytest.approx(expected) if expected else None)


def test_full_staffing_creates_no_exception_rows_at_all(client):
    create_plant(client, staffing=(1.0, 0, 0, 0))
    r = client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=1, year=2026)).json()
    assert r["holidays_imported"] == 0 and client.get("/team-week-exceptions").json() == []


def test_a_seven_day_plant_loses_less_per_stopped_day(client):
    create_plant(client)
    client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=4, year=2026, working_days_per_week=7))
    assert week_multiplier(client, 4, WEEK_38) == pytest.approx(1 - 1 / 7)


def test_importing_holidays_twice_does_not_stack(client):
    create_plant(client)
    first = client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=4, year=2026)).json()
    again = client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=4, year=2026)).json()
    assert first["holidays_imported"] == 7 and again["holidays_imported"] == 0
    assert week_multiplier(client, 4, WEEK_38) == pytest.approx(0.8)


def test_a_holiday_stacks_on_a_manual_exception(client):
    create_plant(client)
    client.post("/team-week-exceptions", params=dict(team_id=4, year=2026, week_number=WEEK_38, capacity_multiplier=0.9, reason="Mantenimiento"))
    client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=4, year=2026))
    assert week_multiplier(client, 4, WEEK_38) == pytest.approx(0.7)       # 0.9 - 0.2


def test_2026_has_the_seven_federal_holidays_and_no_october_first():
    from mexican_holidays import get_mexican_holidays
    days = [d.isoformat() for d, _ in get_mexican_holidays(2026)]
    assert days == ["2026-01-01", "2026-02-02", "2026-03-16", "2026-05-01", "2026-09-16", "2026-11-16", "2026-12-25"]
    assert any(d.month == 10 and d.day == 1 for d, _ in get_mexican_holidays(2024))    # transition year
    assert not any(d.month == 10 and d.day == 1 for d, _ in get_mexican_holidays(2027))


# ---------- random productivity drops ----------

def test_the_same_seed_always_picks_the_same_weeks():
    assert draw_disruptions([1, 2, 3, 4], seed=7) == draw_disruptions([1, 2, 3, 4], seed=7)
    assert draw_disruptions([1, 2, 3, 4], seed=7) != draw_disruptions([1, 2, 3, 4], seed=8)


def test_a_higher_probability_keeps_every_earlier_hit():
    low = {(t, w) for t, w, _ in draw_disruptions([1, 2, 3, 4], probability=0.10, seed=7)}
    high = {(t, w) for t, w, _ in draw_disruptions([1, 2, 3, 4], probability=0.30, seed=7)}
    assert low <= high and len(high) > len(low)


def test_ten_percent_means_about_ten_percent():
    hits = [len(draw_disruptions([1, 2, 3, 4], seed=s)) for s in range(300)]
    assert 19 < statistics.mean(hits) < 22.6              # 4 teams x 52 weeks x 10% = 20.8


def test_drops_stay_inside_the_requested_range():
    drops = [d for s in range(50) for _, _, d in draw_disruptions([1, 2, 3, 4], probability=1, min_drop=0.2, max_drop=0.3, seed=s)]
    assert min(drops) >= 0.2 and max(drops) <= 0.3


def test_endpoint_probability_extremes(client):
    create_plant(client)
    assert client.post("/team-week-exceptions/generate-disruptions", params=dict(year=2026, probability=0, seed=1)).json()["weeks_affected"] == 0
    r = client.post("/team-week-exceptions/generate-disruptions", params=dict(year=2025, probability=1, seed=1, team_id=2)).json()
    assert r["weeks_affected"] == 52 and r["by_team"] == {"2": 52}


def test_endpoint_is_reproducible_and_re_runnable(client):
    create_plant(client)
    first = client.post("/team-week-exceptions/generate-disruptions", params=dict(year=2026, seed=7)).json()
    again = client.post("/team-week-exceptions/generate-disruptions", params=dict(year=2026, seed=7)).json()
    assert first["weeks_affected"] > 0 and again["weeks_affected"] == 0           # second click changes nothing
    multipliers = [float(e["capacity_multiplier"]) for e in client.get("/team-week-exceptions").json()]
    assert min(multipliers) >= 0.6 - 1e-9 and max(multipliers) <= 0.9 + 1e-9      # default drops: 10% to 40%


def test_a_drop_stacks_on_a_holiday_week(client):
    create_plant(client)
    client.post("/team-week-exceptions/import-mexican-holidays", params=dict(team_id=4, year=2026))
    client.post("/team-week-exceptions/generate-disruptions", params=dict(year=2026, team_id=4, probability=1, min_drop=0.1, max_drop=0.1))
    assert week_multiplier(client, 4, WEEK_38) == pytest.approx(0.7)              # 1 - 0.2 - 0.1
