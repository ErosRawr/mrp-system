"""
Seed the MRP system with test data via the running HTTP API, including
enough orders on the same team to actually exercise capacity contention
and FIFO scheduling.

Usage:
    1. Start the backend:  uvicorn main:app --reload
    2. Run this script:    python seed_data.py
"""

import requests
from datetime import date, timedelta

BASE = "http://localhost:8000"

counts = {"teams": 0, "schedule": 0, "inventory": 0, "orders": 0, "scheduled": 0}


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
            print(f"  {label}: FAILED {resp.status_code} — {resp.text}")
        else:
            print(f"  {label}: FAILED — {e}")
        return None


# -- 1. Teams --

TEAMS = [
    {"name": "Melting",     "sequence_order": 1, "daily_capacity": 1200, "efficiency": 0.97},
    {"name": "Casting",     "sequence_order": 2, "daily_capacity": 1150, "efficiency": 0.95},
    {"name": "Hot Rolling", "sequence_order": 3, "daily_capacity": 1100, "efficiency": 0.96},
    {"name": "Finishing",   "sequence_order": 4, "daily_capacity": 300,  "efficiency": 0.98},
    # Finishing capacity deliberately kept LOW (300/day) so a handful of
    # orders is enough to create real contention/backlog to observe.
]

print("Creating teams ...")
team_ids = {}
for t in TEAMS:
    data = post("/teams", t, f"Created team: {t['name']}")
    if data:
        team_ids[t["name"]] = data["id"]
        counts["teams"] += 1

print()

# -- 2. Weekly Schedule (Mon-Fri working, Sat-Sun off) --

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

print("Setting weekly schedules ...")
for name, tid in team_ids.items():
    for day in range(7):
        working = day <= 4
        data = post(
            "/team-weekly-schedule",
            {"team_id": tid, "day_of_week": day, "is_working_day": working},
            f"{name} {DAY_NAMES[day]}={'work' if working else 'off'}",
        )
        if data:
            counts["schedule"] += 1

print()

# -- 3. Inventory --

INVENTORY = {"Melting": 0, "Casting": 200, "Hot Rolling": 0, "Finishing": 50}

print("Setting inventory ...")
for name, qty in INVENTORY.items():
    tid = team_ids.get(name)
    if tid is None:
        continue
    data = post("/inventory", {"team_id": tid, "quantity_on_hand": qty}, f"{name}: {qty} on hand")
    if data:
        counts["inventory"] += 1

print()

# -- 4. Orders: enough to create real contention at Finishing --
# Finishing capacity is 300/day. Each order below requests 250 units
# entering at Finishing, so every order eats most of a day's capacity --
# with several orders on the same order_date, later ones should visibly
# get pushed to later dates.

today = date.today()

ORDERS = [
    {"customer_name": f"Customer {i+1}", "quantity_requested": 250,
     "entry_team_id": team_ids.get("Finishing"),
     "order_date": today.isoformat(),
     "due_date": (today + timedelta(days=14)).isoformat()}
    for i in range(8)  # 8 same-day orders competing for 300/day capacity
]

print("Creating orders ...")
order_ids = []
for o in ORDERS:
    data = post("/orders", o, f"Order for {o['customer_name']} (qty {o['quantity_requested']})")
    if data:
        order_ids.append(data["id"])
        counts["orders"] += 1

print()

# -- 5. Schedule each order in creation sequence (FIFO) --

print("Scheduling orders (FIFO by creation order) ...")
for oid in order_ids:
    try:
        r = requests.post(f"{BASE}/orders/{oid}/schedule")
        r.raise_for_status()
        result = r.json()
        finishing_step = next(
            (s for s in result["schedule"] if s["team_name"] == "Finishing"), None
        )
        if finishing_step:
            print(f"  Order {oid}: Finishing scheduled {finishing_step['start_date']} -> {finishing_step['end_date']}")
        counts["scheduled"] += 1
    except Exception as e:
        print(f"  Order {oid}: FAILED -- {e}")

print()

# -- Summary --

print("--- Seed complete ---")
print(f"Teams:                   {counts['teams']} created")
print(f"Weekly schedule entries: {counts['schedule']} created")
print(f"Inventory rows:          {counts['inventory']} created")
print(f"Orders:                  {counts['orders']} created")
print(f"Orders scheduled:        {counts['scheduled']}")
print()
print("Check GET /teams/{id}/capacity-allocations for the Finishing team")
print("to see the full day-by-day breakdown of how orders queued up.")