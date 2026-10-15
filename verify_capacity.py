import sys
from collections import defaultdict


def verify(get):
    teams = get("/teams")
    excs = get("/team-week-exceptions")
    mult = {(e["team_id"], e["year"], e["week_number"]): float(e["capacity_multiplier"]) for e in excs}

    bad = 0
    for t in teams:
        allocs = get(f"/teams/{t['id']}/capacity-allocations")
        per_week = defaultdict(float)
        for a in allocs:
            per_week[(a["year"], a["week_number"])] += float(a["quantity_allocated"])
        for (y, w), used in sorted(per_week.items()):
            cap = t["weekly_capacity"] * mult.get((t["id"], y, w), 1.0)
            if used > cap + 0.01:
                bad += 1
                print(f"OVER: {t['name']} {y}-W{w}: {used:.0f} > {cap:.0f}")
    print("All weeks within effective capacity" if bad == 0 else f"{bad} violation(s)")
    return bad


if __name__ == "__main__":
    import requests
    BASE = "http://localhost:8000"
    sys.exit(1 if verify(lambda p: requests.get(BASE + p).json()) else 0)
