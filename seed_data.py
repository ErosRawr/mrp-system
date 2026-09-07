"""
Seed the MRP system with realistic test data via the running HTTP API.

Usage:
    1. Start the backend:  uvicorn main:app --reload
    2. Run this script:    python seed_data.py
"""

import requests
from datetime import date, timedelta

BASE = "http://localhost:8000"

# ── Counters ──────────────────────────────────────────────────────────────────

counts = {"teams": 0, "schedule": 0, "inventory": 0, "orders": 0}


def post(path, params, label):
    """POST to the API with query params. Returns the JSON response or None."""
    try:
        r = requests.post(f"{BASE}{path}", params=params)
        r.raise_for_status()
        data = r.json()
        print(f"  {label}: OK")
        return data
    except Exception as e:
        status = getattr(e, "response", None)
        if status is not None:
            print(f"  {label}: FAILED {status.status_code} — {status.text}")
        else:
            print(f"  {label}: FAILED — {e}")
        return None


# ── 1. Teams ──────────────────────────────────────────────────────────────────

TEAMS_EXISTING = {
    "Melting": 1,
    "Casting": 2,
    "Hot Rolling": 3,
    "Finishing": 4,
}

print("Using existing teams …")
team_ids = TEAMS_EXISTING
for name, tid in team_ids.items():
    print(f"  {name} (id={tid})")
counts["teams"] = len(team_ids)

print()

# ── 2. Weekly Schedule ───────────────────────────────────────────────────────

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

print("Setting weekly schedules …")
for name, tid in team_ids.items():
    for day in range(7):
        working = day <= 4  # Mon–Fri
        data = post(
            "/team-weekly-schedule",
            {"team_id": tid, "day_of_week": day, "is_working_day": working},
            f"{name} {DAY_NAMES[day]}={'work' if working else 'off'}",
        )
        if data:
            counts["schedule"] += 1

print()

# ── 3. Inventory ──────────────────────────────────────────────────────────────

INVENTORY = {
    "Melting":     0,
    "Casting":     200,
    "Hot Rolling": 0,
    "Finishing":   50,
}

print("Setting inventory …")
for name, qty in INVENTORY.items():
    tid = team_ids.get(name)
    if tid is None:
        print(f"  Skipping {name} (team not created)")
        continue
    data = post(
        "/inventory",
        {"team_id": tid, "quantity_on_hand": qty},
        f"{name}: {qty} on hand",
    )
    if data:
        counts["inventory"] += 1

print()

# ── 4. Orders ─────────────────────────────────────────────────────────────────

today = date.today()

ORDERS = [
    {
        "customer_name":     "Acme Construction",
        "quantity_requested": 1000,
        "entry_team_id":     team_ids.get("Finishing"),
        "order_date":        today.isoformat(),
        "due_date":          (today + timedelta(days=21)).isoformat(),
    },
    {
        "customer_name":     "Bridgeworks Inc",
        "quantity_requested": 500,
        "entry_team_id":     team_ids.get("Hot Rolling"),
        "order_date":        today.isoformat(),
        "due_date":          (today + timedelta(days=14)).isoformat(),
    },
]

print("Creating orders …")
for o in ORDERS:
    if o["entry_team_id"] is None:
        print(f"  Skipping order for {o['customer_name']} (entry team not created)")
        continue
    data = post(
        "/orders",
        o,
        f"Order for {o['customer_name']} (qty {o['quantity_requested']})",
    )
    if data:
        counts["orders"] += 1

print()

# ── Summary ───────────────────────────────────────────────────────────────────

print("--- Seed complete ---")
print(f"Teams:                  {counts['teams']} created")
print(f"Weekly schedule entries: {counts['schedule']} created")
print(f"Inventory rows:         {counts['inventory']} created")
print(f"Orders:                 {counts['orders']} created")
