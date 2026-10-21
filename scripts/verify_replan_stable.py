"""
Checks that the committed plans are consistent with planning in calendar
order: re-planning everything from scratch must change nothing. If it does,
some month was planned against stale capacity.

Run with the server up, on a seeded database:
    python scripts/verify_replan_stable.py
"""
import requests

BASE = "http://localhost:8000"


def snapshot():
    return {o["id"]: o["calculated_delivery_date"] for o in requests.get(f"{BASE}/orders").json()}


before = snapshot()
response = requests.post(f"{BASE}/planning/replan-all")
if response.status_code == 404:
    raise SystemExit(
        "The server has no /planning/replan-all endpoint: it is still running the old backend.\n"
        "Copy the updated main.py, models.py, planning.py and disruptions.py into the project root,\n"
        "delete mrp.db, restart uvicorn, and run scripts/seed_data.py again."
    )
response.raise_for_status()
months = response.json()["months_replanned"]
after = snapshot()

changed = [i for i in before if before[i] != after[i]]
print(f"re-planned {len(months)} month(s) in calendar order")
print("STABLE" if not changed else f"UNSTABLE: {len(changed)} order(s) changed, e.g. ids {changed[:5]}")