"""
Demo data for the MRP system.

Two goals:
  1. September 2026 is HAND-BUILT so the three planning criteria (PEPS,
     Prioritario, Heuristica) produce visibly different results, each
     defensible for a different reason (see SEPTEMBER_ORDERS).
  2. The other eleven months are a "good run": most orders on time, with a
     few late and critically-late orders scattered through the year.

Plant model used to size everything:
  * Equipo 4 is the bottleneck: 100,000 t/month = 25,000 t/week.
  * Every order walks Equipo 1 -> 2 -> 3 -> 4, one team per week at best, so
    the fastest possible delivery is ~4 weeks after the order date.
  * "Slack" below = requested delivery date minus that fastest possible date.
    Slack >= 0 is reachable on a quiet plant; negative slack is a rush the
    plant cannot meet no matter what.

September and the rest of the year are all created at Equipo 4 (the entry
point of the bottleneck) so every order genuinely competes for its capacity.

Usage (from the project root):
    1. Start the backend:  uvicorn main:app --reload
    2. Run this script:    python scripts/seed_data.py
"""

import random
import requests
from datetime import date, timedelta

BASE = "http://localhost:8000"
YEAR, MONTH = 2026, 9           # MONTH = the month left for the live demo

random.seed(7)  # reproducible -- same orders every run

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


# -- 1. Teams: sized for the tonnage below. Efficiencies are unchanged, so
# the material-requirements example (100 t of finished steel needs ~121.6 t
# of raw input) still holds -- it only depends on efficiency, not capacity.
# Equipo 4 stays the bottleneck (25,000 t/week); upstream teams have headroom.

TEAMS = [
    {"name": "Equipo 1", "sequence_order": 1, "monthly_capacity": 260000, "efficiency": 0.98},
    {"name": "Equipo 2", "sequence_order": 2, "monthly_capacity": 200000, "efficiency": 0.95},
    {"name": "Equipo 3", "sequence_order": 3, "monthly_capacity": 160000, "efficiency": 0.92},
    {"name": "Equipo 4", "sequence_order": 4, "monthly_capacity": 100000, "efficiency": 0.96},
]

print("Creando equipos...")
team_ids = {}
for t in TEAMS:
    data = post("/teams", t, f"Equipo creado: {t['name']}")
    if data:
        team_ids[t["name"]] = data["id"]
        counts["teams"] += 1
print()

ENTRY_TEAM = team_ids["Equipo 4"]


def fastest_delivery_days(order_date):
    """Days from order_date to the earliest possible delivery: the Sunday of
    the ISO week that is 3 weeks after the order's week (one team per week)."""
    iso_year, iso_week, _ = order_date.isocalendar()
    monday = date.fromisocalendar(iso_year, iso_week, 1) + timedelta(weeks=3)
    return (monday + timedelta(days=6) - order_date).days


def create_order(month, customer, qty, lead_days, priority=False, tipo=None):
    order_date = date(YEAR, month, 1)
    params = {
        "customer_name": customer,
        "quantity_requested": qty,
        "entry_team_id": ENTRY_TEAM,
        "order_date": order_date.isoformat(),
        "requested_delivery_date": (order_date + timedelta(days=lead_days)).isoformat(),
        "planning_year": YEAR,
        "planning_month": month,
        "is_priority": priority,
        "tipo_pedido": tipo,
    }
    data = post("/orders", params, quiet=True)
    if data:
        counts["orders"] += 1
    return data


# -- 2. SEPTEMBER: hand-built. 18 orders, ~91,000 t against ~100,000 t of
# bottleneck capacity before Oct 19, with requests bunched into a late-Sep /
# early-Oct rush. Lead days are counted from Sep 1 (fastest possible: day 26).
#
# What each criterion does with it:
#   PEPS         (by requested date)   best for the small, early requests;
#                                      leaves the priority customers and the
#                                      two big orders waiting at the back.
#   Prioritario  (priority first)      rescues Cliente VIP and Constructora
#                                      Premium at almost no cost to anyone.
#   Heuristica   (priority, then 15k+  also rescues Pedido Grande and Gran
#                 tons, then tipo)     Obra, paid for by the small low-rank
#                                      orders (especial, perfileros...).

SEPTEMBER_ORDERS = [
    # customer,               tons, lead_days, priority, tipo
    ("Urgente Tardio",        3500, 22, False, "especial"),
    ("Taller Mecanico",       1500, 42, False, "ojalatero"),
    ("Herreria del Norte",    2000, 30, False, "especial"),
    ("Comercial Sureste",     3000, 27, False, "comercial"),
    ("Ferreteria Central",    2500, 37, False, "comercial"),
    ("Perfilados Bravo",      4000, 26, False, "perfileros"),
    ("Galvanizados Reyes",    3500, 26, False, "galvanizado"),
    ("Tubos del Golfo",       2200, 45, False, "tuberia"),
    ("Aceros del Pacifico",   5000, 27, False, "comercial"),
    ("Metalurgica Saltillo",  4500, 28, False, "perfiles"),
    ("Fundidora Regional",    3000, 26, False, "perfileros"),
    ("Estructuras Norte",     6000, 27, False, "galvanizado"),
    ("Laminados del Bajio",   2800, 45, False, "tuberia"),
    ("Ojalateria Central",    1800, 45, False, "ojalatero"),
    ("Pedido Grande",        18000, 28, False, "tuberia"),
    ("Gran Obra Federal",    16500, 31, False, "perfiles"),
    ("Cliente VIP",           4000, 32, True,  "comercial"),
    ("Constructora Premium",  7500, 28, True,  "galvanizado"),
]
# Storyline orders worth pointing at in the demo:
#   "Urgente Tardio"       earliest request: first in PEPS, near the back in Heuristica
#   "Cliente VIP"          priority, latest of the rush: critical in PEPS, first in the others
#   "Pedido Grande"        18,000 t: late in PEPS, 3rd in Heuristica
#   "Gran Obra Federal"    16,500 t: critical in PEPS, 4th in Heuristica

print(f"Creando pedidos de {YEAR}-{MONTH:02d} (hechos a mano)...")
for customer, qty, lead, priority, tipo in SEPTEMBER_ORDERS:
    create_order(MONTH, customer, qty, lead, priority, tipo)
print(f"  {len(SEPTEMBER_ORDERS)} pedidos.")
print()

# -- 3. REST OF THE YEAR: a good run. Each month gets a batch of ordinary
# orders (tonnage mix below) with comfortable slack, so almost everything
# is on time, plus a few scripted trouble spots in MONTH_EVENTS.

CUSTOMER_NAMES = [
    "Aceros del Norte", "Construcciones Monclova", "Grupo Ferroindustrial",
    "Metalurgica Coahuila", "Industrias Saltillo", "Perfiles del Bravo",
    "Aceros Torreon", "Constructora Regiomontana", "Fundidora del Centro",
    "Acero y Forja SA", "Metales Especializados", "Grupo Siderurgico MX",
    "Estructuras del Norte", "Laminados Industriales", "Perfilados Coahuila",
    "Tuberia Industrial MX", "Galvanizados del Bravo", "Comercial Acerera",
    "Ojalateria Central", "Especiales del Norte",
]
TIPOS = ["comercial", "galvanizado", "perfiles", "perfileros", "tuberia", "ojalatero", "especial"]

# (orders in the month, slack range in days) -- tight slack = customers all
# want it at once, which is how a busy month produces late orders.
MONTH_PROFILE = {
    1: (12, (10, 30)),  2: (13, (10, 30)),  3: (13, (10, 30)),  4: (14, (0, 9)),
    5: (13, (10, 30)),  6: (13, (10, 30)),  7: (14, (1, 11)),   8: (12, (10, 30)),
    10: (13, (10, 30)), 11: (12, (10, 30)), 12: (14, (6, 22)),
}

# Scripted trouble: (customer, tons, slack_days, priority, tipo). Negative slack
# is a rush the plant cannot meet: about -9 -> late, about -17 -> critically late.
MONTH_EVENTS = {
    3:  [("Aceros Torreon", 5200, -18, False, "perfileros")],
    2:  [("Fundidora del Centro", 3200, -9, False, "tuberia")],
    6:  [("Constructora Regiomontana", 4800, -17, False, "comercial")],
    8:  [("Acero y Forja SA", 2600, -11, False, "galvanizado")],
    10: [("Metales Especializados", 3600, -10, False, "perfiles")],
    12: [("Grupo Siderurgico MX", 15500, 3, False, "tuberia"),
         ("Estructuras del Norte", 4200, -16, False, "comercial")],
}


def ordinary_tons(rng):
    # ~2/3 small, ~1/3 medium
    if rng.random() < 0.68:
        return rng.randint(1200, 6000)
    return rng.randint(6000, 11000)


print(f"Creando pedidos del resto de {YEAR}...")
for month in range(1, 13):
    if month == MONTH:
        continue
    n, (slack_lo, slack_hi) = MONTH_PROFILE[month]
    fastest = fastest_delivery_days(date(YEAR, month, 1))
    rng = random.Random(YEAR * 100 + month)  # one stream per month: tune a month without moving the others
    for _ in range(n):
        tipo = rng.choice(TIPOS)
        priority = rng.random() < 0.06
        qty = ordinary_tons(rng)
        slack = rng.randint(slack_lo, slack_hi)
        customer = rng.choice(CUSTOMER_NAMES)
        create_order(month, customer, qty, fastest + slack, priority, tipo)
    for customer, qty, slack, priority, tipo in MONTH_EVENTS.get(month, []):
        create_order(month, customer, qty, fastest + slack, priority, tipo)
print(f"  {counts['orders'] - len(SEPTEMBER_ORDERS)} pedidos.")
print()

# -- 4. Holidays for Equipo 4 (a holiday week runs at 80% capacity).

print("Importando dias festivos para Equipo 4...")
post("/team-week-exceptions/import-mexican-holidays",
     {"team_id": ENTRY_TEAM, "year": YEAR}, "Equipo 4: festivos importados")
print()

# -- 5. Plan every month EXCEPT September, in order, with PEPS. September
# stays unplanned for the live demo. Its comparison is not distorted by the
# other months: October's orders only reach the bottleneck after Oct 19,
# and September's work is finished by then under all three criteria.

print("Ejecutando planeacion mensual (PEPS), todos los meses menos septiembre...")
for month in range(1, 13):
    if month == MONTH:
        print(f"  {YEAR}-{month:02d}: omitido -- se compara y se guarda en la demo")
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
print(f"Pedidos: {counts['orders']} ({len(SEPTEMBER_ORDERS)} de septiembre + {counts['orders'] - len(SEPTEMBER_ORDERS)} del resto del ano)")
print(f"Planeacion (PEPS) ejecutada para todos los meses excepto {YEAR}-{MONTH:02d}.")
print()
print("Guion de la demo:")
print(f"  1. Heuristica -> Comparar el mes {YEAR}-{MONTH:02d} (no guarda nada). Busca:")
print('     - "Urgente Tardio": primero en PEPS, casi al final en Heuristica')
print('     - "Cliente VIP": critico en PEPS, primero en Prioritario y Heuristica')
print('     - "Pedido Grande" y "Gran Obra Federal": atrasados en PEPS, rescatados por Heuristica')
print("  2. Elige un criterio y pulsa Ejecutar y guardar para septiembre.")
print(f"  3. Dashboard: usa el mes 8 (o cualquier mes menos {MONTH}) para ver datos antes del paso 2.")