"""
Seed a full year of realistic demo data: the professor's own team
numbers, plus ~100 orders spread across all 12 months (all 4 quarters),
with randomized-but-plausible quantities and requested delivery dates,
then runs the monthly planning batch for every month so the dashboard,
quarterly charts, and occupancy views all have real data to show.

This is separate from seed_data.py (which is the small, deterministic
scenario used to verify the FIFO/contention logic in isolation) --
this script is specifically for producing a rich, demo-ready dataset.

Usage:
    1. Start the backend:  uvicorn main:app --reload
    2. Run this script:    python seed_demo_data.py
"""

import random
import requests
from datetime import date, timedelta

BASE = "http://localhost:8000"

random.seed(42)  # reproducible demo data -- same run every time

counts = {"teams": 0, "orders": 0, "months_planned": 0}


def post(path, params, label=None, quiet=False):
    try:
        r = requests.post(f"{BASE}{path}", params=params)
        r.raise_for_status()
        data = r.json()
        if label and not quiet:
            print(f"  {label}: OK")
        return data
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None:
            print(f"  {label or path}: FAILED {resp.status_code} -- {resp.text}")
        else:
            print(f"  {label or path}: FAILED -- {e}")
        return None


# -- 1. Teams -- exactly the professor's worked example --

TEAMS = [
    {"name": "Equipo 1", "sequence_order": 1, "monthly_capacity": 100000, "efficiency": 0.98},
    {"name": "Equipo 2", "sequence_order": 2, "monthly_capacity": 80000,  "efficiency": 0.95},
    {"name": "Equipo 3", "sequence_order": 3, "monthly_capacity": 80000,  "efficiency": 0.92},
    {"name": "Equipo 4", "sequence_order": 4, "monthly_capacity": 50000,  "efficiency": 0.96},
]

print("Creando equipos...")
team_ids = {}
for t in TEAMS:
    data = post("/teams", t, f"Equipo creado: {t['name']}")
    if data:
        team_ids[t["name"]] = data["id"]
        counts["teams"] += 1

print()

# -- 2. Import Mexican holidays for every team for 2026 --

print("Importando dias festivos mexicanos 2026 para cada equipo...")
for name, tid in team_ids.items():
    post("/team-week-exceptions/import-mexican-holidays",
         {"team_id": tid, "year": 2026}, f"{name}: festivos importados", quiet=True)

print()

# -- 3. ~100 orders spread across all 12 months of 2026 --
# Entry team is randomized across teams so different orders exercise
# different parts of the chain -- some orders only need the last team,
# some need the whole route. Quantities vary so some months are light
# and some push close to capacity (visible in the dashboard/occupancy).

CUSTOMER_NAMES = [
    "Aceros del Norte", "Construcciones Monclova", "Grupo Ferroindustrial",
    "Metalurgica Coahuila", "Industrias Saltillo", "Perfiles del Bravo",
    "Aceros Torreon", "Constructora Regiomontana", "Fundidora del Centro",
    "Acero y Forja SA", "Metales Especializados", "Grupo Siderurgico MX",
    "Estructuras del Norte", "Laminados Industriales", "Perfilados Coahuila",
]

YEAR = 2026
TEAM_NAMES = list(team_ids.keys())

print("Creando ~100 pedidos distribuidos en los 12 meses del 2026...")
order_ids = []
orders_per_month_target = 8  # ~8/month x 12 = ~96 orders

for month in range(1, 13):
    for _ in range(orders_per_month_target):
        entry_team_name = random.choice(TEAM_NAMES)
        # Bias quantities toward Equipo 4's realistic weekly scale (~12,500)
        # so orders entering there create visible contention; orders
        # entering earlier teams can be larger since those teams have
        # much higher capacity.
        if entry_team_name == "Equipo 4":
            qty = random.randint(800, 3000)
        elif entry_team_name in ("Equipo 2", "Equipo 3"):
            qty = random.randint(1000, 5000)
        else:
            qty = random.randint(1500, 8000)

        order_day = random.randint(1, 25)  # leave room for delivery date to stay in-month-ish
        order_date = date(YEAR, month, order_day)

        # Requested delivery: somewhere between 5 and 25 days after order_date
        requested_delivery = order_date + timedelta(days=random.randint(5, 25))

        customer = random.choice(CUSTOMER_NAMES)

        params = {
            "customer_name": customer,
            "quantity_requested": qty,
            "entry_team_id": team_ids[entry_team_name],
            "order_date": order_date.isoformat(),
            "requested_delivery_date": requested_delivery.isoformat(),
            "planning_year": YEAR,
            "planning_month": month,
        }
        data = post("/orders", params, quiet=True)
        if data:
            order_ids.append(data["id"])
            counts["orders"] += 1

print(f"  {counts['orders']} pedidos creados.")
print()

# -- 4. Run monthly planning for every month that has orders --

print("Ejecutando planeacion mensual para cada mes...")
for month in range(1, 13):
    r = requests.post(f"{BASE}/planning/run", params={"year": YEAR, "month": month})
    if r.status_code == 200:
        result = r.json()
        if result["orders_planned"] > 0:
            late_count = sum(1 for x in result["results"] if x.get("is_late") is True)
            print(f"  {YEAR}-{month:02d}: {result['orders_planned']} pedidos planeados, {late_count} atrasados")
            counts["months_planned"] += 1
    else:
        print(f"  {YEAR}-{month:02d}: FAILED -- {r.status_code} {r.text}")

print()

# -- Summary --

print("--- Seed completo ---")
print(f"Equipos:          {counts['teams']}")
print(f"Pedidos:          {counts['orders']}")
print(f"Meses planeados:  {counts['months_planned']}")
print()
print("El dashboard, las graficas trimestrales, el calendario y la vista")
print("de ocupacion ahora tienen datos reales distribuidos en todo el 2026.")