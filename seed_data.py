"""
Seed data designed to showcase the three planning criteria (PEPS,
Prioritario, Heuristica) producing visibly DIFFERENT results, at a
realistic volume (100+ orders).

Two parts:
  1. A handful of hand-crafted "storyline" orders, each built to make a
     specific point about how the criteria disagree (see comments below).
     These are the ones worth pointing at directly in a demo.
  2. ~100 additional randomized orders (reproducible via a fixed seed)
     to give the month realistic volume -- so the dashboard, occupancy,
     and quarterly views all have something substantial to show, and so
     the storyline orders are proven to still behave correctly even
     amid a busy, contested month rather than in an artificially empty one.

All orders enter at Equipo 4 (the bottleneck, weekly capacity ~12,500
tons with the professor's numbers) so they genuinely compete for the
same capacity.

Usage:
    1. Start the backend:  uvicorn main:app --reload
    2. Run this script:    python seed_heuristic_demo.py
"""

import random
import requests
from datetime import date

BASE = "http://localhost:8000"

random.seed(7)  # reproducible -- same 100+ orders every run

counts = {"teams": 0, "orders": 0}


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


# -- 1. Teams -- professor's exact worked example --

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

YEAR, MONTH = 2026, 9
ORDER_DATE = date(YEAR, MONTH, 1).isoformat()
TIPOS = ["comercial", "galvanizado", "perfiles", "perfileros", "tuberia", "ojalatero", "especial"]

# -- 2. Storyline orders -- hand-crafted to make the three criteria
# visibly disagree. These are worth pointing at directly in a demo.

STORYLINE_ORDERS = [
    # name, qty, requested_day, is_priority, tipo_pedido
    ("Urgente Tardio",   4000, 3,  False, "especial"),
    # ^ earliest requested date, but lowest-rank tipo and no priority:
    #   PEPS puts this FIRST; Heuristica pushes it toward the back.

    ("Cliente VIP",      3500, 28, True,  "comercial"),
    # ^ latest requested date of the storyline batch, but is_priority=True:
    #   PEPS puts this near LAST; Prioritario and Heuristica put it FIRST.

    ("Pedido Grande",    18000, 15, False, "tuberia"),
    # ^ above the 15k threshold -- Heuristica ranks this near the top
    #   purely on tonnage, even without priority.
]

print("Creando pedidos de historia (storyline)...")
storyline_customer_names = set()
for name, qty, day, priority, tipo in STORYLINE_ORDERS:
    storyline_customer_names.add(name)
    params = {
        "customer_name": name,
        "quantity_requested": qty,
        "entry_team_id": team_ids["Equipo 4"],
        "order_date": ORDER_DATE,
        "requested_delivery_date": date(YEAR, MONTH, day).isoformat(),
        "planning_year": YEAR,
        "planning_month": MONTH,
        "is_priority": priority,
        "tipo_pedido": tipo,
    }
    data = post("/orders", params, f"{name} (qty={qty}, prioridad={priority}, tipo={tipo})")
    if data:
        counts["orders"] += 1

print()

# -- 3. ~100 additional randomized orders, spread across ALL 12 months
# of the year -- not just September. This gives the Dashboard's
# quarterly charts, the yearly Calendar view, and Occupancy all real
# data to show across the full year, not just one month. The storyline
# orders above stay anchored in September specifically so there's still
# one clearly "busy" month to run the Heuristica comparison against.
#
# Mostly non-priority, varied tonnage and tipo. A small minority (about
# 8%) are randomly priority, so Prioritario/Heuristica have real
# contenders to reshuffle beyond just the storyline orders, in whatever
# month they land in.

CUSTOMER_NAMES = [
    "Aceros del Norte", "Construcciones Monclova", "Grupo Ferroindustrial",
    "Metalurgica Coahuila", "Industrias Saltillo", "Perfiles del Bravo",
    "Aceros Torreon", "Constructora Regiomontana", "Fundidora del Centro",
    "Acero y Forja SA", "Metales Especializados", "Grupo Siderurgico MX",
    "Estructuras del Norte", "Laminados Industriales", "Perfilados Coahuila",
    "Tuberia Industrial MX", "Galvanizados del Bravo", "Comercial Acerera",
    "Ojalateria Central", "Especiales del Norte",
]

TOTAL_RANDOM_ORDERS = 100
ORDERS_PER_MONTH = TOTAL_RANDOM_ORDERS // 12  # ~8/month x 12 = ~96, plus remainder below

print(f"Creando {TOTAL_RANDOM_ORDERS} pedidos adicionales distribuidos en los 12 meses del {YEAR}...")
random_created = 0

for month in range(1, 13):
    # Give the remainder months (if TOTAL_RANDOM_ORDERS doesn't divide
    # evenly by 12) one extra order each, so the total still adds up.
    this_month_count = ORDERS_PER_MONTH + (1 if month <= (TOTAL_RANDOM_ORDERS % 12) else 0)

    month_order_date = date(YEAR, month, 1).isoformat()

    for _ in range(this_month_count):
        tipo = random.choice(TIPOS)
        is_priority = random.random() < 0.08  # ~8% priority, a real minority

        # Tonnage: mostly modest, occasionally above the 15k heuristic
        # threshold so there's real tonnage-driven contenders beyond
        # "Pedido Grande" alone.
        if random.random() < 0.1:
            qty = random.randint(15000, 25000)  # above threshold
        else:
            qty = random.randint(500, 8000)

        # Keep requested day within a range that stays inside (or close
        # to) the same calendar month, leaving room for delivery dates.
        day = random.randint(2, 25)
        customer = random.choice(CUSTOMER_NAMES)

        params = {
            "customer_name": customer,
            "quantity_requested": qty,
            "entry_team_id": team_ids["Equipo 4"],
            "order_date": month_order_date,
            "requested_delivery_date": date(YEAR, month, day).isoformat(),
            "planning_year": YEAR,
            "planning_month": month,
            "is_priority": is_priority,
            "tipo_pedido": tipo,
        }
        data = post("/orders", params, quiet=True)
        if data:
            random_created += 1
            counts["orders"] += 1

print(f"  {random_created} pedidos aleatorios creados, distribuidos en los 12 meses.")
print()

# -- 4. Import Mexican holidays for Equipo 4 --

print("Importando dias festivos para Equipo 4...")
post("/team-week-exceptions/import-mexican-holidays",
     {"team_id": team_ids["Equipo 4"], "year": YEAR}, "Equipo 4: festivos importados")

print()

# -- 5. Run monthly planning (PEPS, the default) for every month that
# has orders, so the Dashboard, quarterly charts, Calendar, and
# Occupancy views all have calculated_delivery_date data across the
# whole year -- not just September. September specifically is left for
# you to re-run manually in the Heuristica tab to see the storyline
# contrast (running it here with PEPS would just show the PEPS result).

print("Ejecutando planeacion mensual (PEPS) para cada mes...")
for month in range(1, 13):
    if month == MONTH:
        print(f"  {YEAR}-{month:02d}: omitido -- compara este mes en la pestana Heuristica")
        continue
    r = requests.post(f"{BASE}/planning/run", params={"year": YEAR, "month": month, "criterion": "peps"})
    if r.status_code == 200:
        result = r.json()
        print(f"  {YEAR}-{month:02d}: {result['orders_planned']} pedidos planeados")
    else:
        print(f"  {YEAR}-{month:02d}: FAILED -- {r.status_code} {r.text}")

print()

# -- Summary --

print("--- Seed completo ---")
print(f"Equipos: {counts['teams']}")
print(f"Pedidos: {counts['orders']} ({len(STORYLINE_ORDERS)} de historia + {random_created} aleatorios)")
print(f"Pedidos distribuidos en los 12 meses de {YEAR}; planeacion (PEPS) ya ejecutada")
print(f"para todos los meses EXCEPTO {YEAR}-{MONTH:02d}.")
print()
print("Dashboard / graficas trimestrales / calendario / ocupacion: ya tienen datos")
print("reales en todo el ano.")
print()
print(f"Para ver el contraste de criterios, ve a la pestana Heuristica y compara")
print(f"el mes {YEAR}-{MONTH:02d}. Busca estos pedidos de historia:")
print('  - "Urgente Tardio": primero en PEPS, al final en Heuristica')
print('  - "Cliente VIP": casi al final en PEPS, primero en Prioritario y Heuristica')
print('  - "Pedido Grande": cerca del frente en Heuristica por tonelaje (18,000 ton)')