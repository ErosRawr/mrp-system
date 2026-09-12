"""
Seed the MRP system with test data via the running HTTP API, using the
professor's own worked example (4 teams, tonnage figures) plus enough
same-month orders on the bottleneck team to actually exercise weekly
capacity contention during the planning run.

Usage:
    1. Start the backend:  uvicorn main:app --reload
    2. Run this script:    python seed_data.py
"""

import requests
from datetime import date, timedelta

BASE = "http://localhost:8000"

counts = {"teams": 0, "orders": 0}


def post(path, params, label):
    try:
        r = requests.post(f"{BASE}{path}", params=params)
        r.raise_for_status()
        data = r.json()
        print(f"  {label}: OK")
        return data
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None:
            print(f"  {label}: FAILED {resp.status_code} -- {resp.text}")
        else:
            print(f"  {label}: FAILED -- {e}")
        return None


# -- 1. Teams -- matches the professor's worked example exactly, except
# Equipo 4's monthly_capacity is deliberately lowered so a handful of
# same-month orders create visible weekly contention during planning.

TEAMS = [
    {"name": "Equipo 1", "sequence_order": 1, "monthly_capacity": 100000, "efficiency": 0.98},
    {"name": "Equipo 2", "sequence_order": 2, "monthly_capacity": 80000,  "efficiency": 0.95},
    {"name": "Equipo 3", "sequence_order": 3, "monthly_capacity": 80000,  "efficiency": 0.92},
    {"name": "Equipo 4", "sequence_order": 4, "monthly_capacity": 4000,   "efficiency": 0.96},
    # Equipo 4: 4000 tons/month over 4 weeks = 1000 tons/week bottleneck,
    # deliberately tight so several ~1200-ton orders visibly queue up.
]

print("Creating teams ...")
team_ids = {}
for t in TEAMS:
    data = post("/teams", t, f"Created team: {t['name']}")
    if data:
        team_ids[t["name"]] = data["id"]
        counts["teams"] += 1

print()

# -- 2. Orders -- several orders in the same planning month, entering at
# Equipo 4 (the bottleneck), with staggered requested delivery dates so
# the planning run's priority-sorting behavior is visible: orders with
# earlier requested dates should get earlier weeks of capacity.

PLANNING_YEAR = 2026
PLANNING_MONTH = 9
order_date = date(PLANNING_YEAR, PLANNING_MONTH, 1)

ORDERS = [
    {"customer_name": "Cliente C (requests late)",   "quantity_requested": 1200,
     "requested_delivery_date": date(PLANNING_YEAR, PLANNING_MONTH, 25).isoformat()},
    {"customer_name": "Cliente A (requests early)",  "quantity_requested": 1200,
     "requested_delivery_date": date(PLANNING_YEAR, PLANNING_MONTH, 10).isoformat()},
    {"customer_name": "Cliente B (requests middle)", "quantity_requested": 1200,
     "requested_delivery_date": date(PLANNING_YEAR, PLANNING_MONTH, 18).isoformat()},
]

print("Creating orders ...")
order_ids = []
for o in ORDERS:
    params = {
        "customer_name": o["customer_name"],
        "quantity_requested": o["quantity_requested"],
        "entry_team_id": team_ids.get("Equipo 4"),
        "order_date": order_date.isoformat(),
        "requested_delivery_date": o["requested_delivery_date"],
        "planning_year": PLANNING_YEAR,
        "planning_month": PLANNING_MONTH,
    }
    data = post("/orders", params, f"Order for {o['customer_name']} (qty {o['quantity_requested']})")
    if data:
        order_ids.append(data["id"])
        counts["orders"] += 1

print()

# -- 3. Run the monthly planning batch --

print(f"Running monthly planning for {PLANNING_YEAR}-{PLANNING_MONTH:02d} ...")
try:
    r = requests.post(f"{BASE}/planning/run", params={"year": PLANNING_YEAR, "month": PLANNING_MONTH})
    r.raise_for_status()
    result = r.json()
    print(f"  Orders planned: {result['orders_planned']}")
    for entry in result["results"]:
        if "error" in entry:
            print(f"  Order {entry['order_id']} ({entry.get('customer_name')}): ERROR -- {entry['error']}")
        else:
            late_flag = " [LATE]" if entry["is_late"] else ""
            print(f"  {entry['customer_name']}: requested={entry['requested_delivery_date']}, "
                  f"calculated={entry['calculated_delivery_date']}{late_flag}")
except Exception as e:
    print(f"  Planning run FAILED -- {e}")

print()

# -- Summary --

print("--- Seed complete ---")
print(f"Teams:  {counts['teams']} created")
print(f"Orders: {counts['orders']} created")
print()
print("Check GET /teams/{id}/capacity-allocations to see the weekly ledger,")
print(f"or GET /teams/{{id}}/occupancy?year={PLANNING_YEAR}&month={PLANNING_MONTH} for the occupancy chart data.")