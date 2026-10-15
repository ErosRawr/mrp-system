import requests

BASE = "http://localhost:8000"
YEAR, MONTH = 2026, 9

run = requests.post(f"{BASE}/planning/run", params={"year": YEAR, "month": MONTH, "criterion": "peps"}).json()
planner = {}
for r in run["results"]:
    s = r.get("lateness_status")
    planner[s] = planner.get(s, 0) + 1

orders = [o for o in requests.get(f"{BASE}/orders").json()
          if o["planning_year"] == YEAR and o["planning_month"] == MONTH]
api = {}
for o in orders:
    s = o["lateness_status"]
    api[s] = api.get(s, 0) + 1

print("planner:", planner)
print("orders :", api)
print("MATCH" if planner == api else "MISMATCH")
