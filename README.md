# MRP System

> Turn scattered production orders into a clear, capacity-aware plan across every team in the process.

MRP System is a manufacturing planning application built around a multi-team production route. Define teams and their capacity, enter customer orders, calculate material requirements, and schedule production to estimate delivery dates and workload.

## Features

- Configure production teams with sequence, monthly capacity, weekly availability, efficiency, and holiday staffing.
- Create, update, and delete customer orders with requested delivery dates, priority, and order type.
- **Material requirements:** for one order, how much each team must process and how much it scraps; for a whole month, the totals and each team's load against its monthly capacity.
- Plan orders against weekly team capacity and estimate delivery dates. Weeks are ISO weeks, including the 53rd in years that have one.
- Compare three planning criteria before committing a plan:
  - **PEPS (FIFO):** earliest requested delivery date first.
  - **Prioritario:** priority orders first, then requested delivery date.
  - **Heurística:** priority first, followed by large orders (15,000+ tons), order type, and requested delivery date.
- **Manual planning:** arrange a month's orders by hand into Expedite, Estándar and Hold, preview the impact without saving, then save. The sequence is stored, so later replanning rebuilds it as arranged.
- **Gantt view** of any plan: one row per order, one bar per team, with the delivery date colored by lateness.
- Track weekly capacity exceptions, import Mexican holiday impacts, and generate reproducible capacity disruptions through the API.
- Review order lateness, team occupancy, a year calendar of availability, and capacity allocations.

## Planning workflow

1. Create teams in production sequence and set their capacity and efficiency.
2. Add customer orders, including quantity, entry team, and requested delivery date.
3. Review material requirements for an order, or for the whole month.
4. Compare scheduling criteria for a month, or arrange the month by hand.
5. Run the selected plan and review delivery dates, lateness, the Gantt, and team occupancy.

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy
- **Database:** SQLite
- **Frontend:** HTML, CSS, and vanilla JavaScript

## Run locally

You need Python installed.

### 1. Install dependencies

From the repository root:

```bash
python -m venv .venv
```

Activate the virtual environment, then install the backend dependencies:

```bash
pip install -r requirements.txt
```

### 2. Start the API

From the repository root:

```bash
uvicorn main:app --app-dir backend --reload
```

The API is available at [http://localhost:8000](http://localhost:8000). Interactive endpoint documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).

The database file (`mrp.db`) is created in the repository root, wherever you start the server from. You can also `cd backend` and run `uvicorn main:app --reload`.

### 3. Start the frontend

Open a second terminal, change into the `frontend` directory, and serve the static files:

```bash
cd frontend
python -m http.server 5500
```

Then open [http://localhost:5500](http://localhost:5500). The frontend currently connects to the API at `http://localhost:8000`.

### Optional: load demo data

With the API running and a fresh local database, open a third terminal in the repository root and run:

```bash
pip install requests
python scripts/seed_data.py
```

The script creates a sample production route and orders for 2026, imports Mexican holiday impacts, generates seeded capacity disruptions, and plans the other months. It leaves September unplanned so you can compare the scheduling criteria and run the selected plan as a demo. Run it once against a fresh database (delete `mrp.db` first) to avoid duplicate sample records.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a throwaway database and never touch `mrp.db`. They cover the planner (capacity, availability, year-end weeks, month ordering), manual planning, material requirements, input validation, and the demo story the seed data is built to tell.

## Project structure

```text
.
├── backend/                 # FastAPI application
│   ├── main.py              # Endpoints
│   ├── models.py            # SQLAlchemy data models
│   ├── database.py          # SQLite connection and sessions
│   ├── planning.py          # Monthly planning and replanning
│   ├── manual_planning.py   # Hand-arranged plans: preview and save
│   ├── heuristics.py        # Planning order criteria
│   ├── calculations.py      # Material requirements (per order and per month)
│   ├── capacity.py          # Weekly capacity helpers
│   ├── lateness.py          # Delivery lateness classification
│   ├── validation.py        # Input validation
│   ├── disruptions.py       # Reproducible disruption generation
│   └── mexican_holidays.py  # Mexican holiday calendar
├── frontend/
│   ├── css/                 # One stylesheet per area of the interface
│   ├── js/                  # One script per view
│   └── index.html           # Main browser app
├── scripts/                 # Talk to a running API over HTTP
│   ├── seed_data.py         # Demo data
│   ├── verify_capacity.py
│   ├── verify_lateness.py
│   └── verify_replan_stable.py
├── tests/                   # pytest suite
├── pytest.ini
├── requirements.txt         # Backend dependencies
└── requirements-dev.txt     # Test and script dependencies
```

## Verification scripts

`scripts/` also holds checks for capacity allocations, lateness reporting, and replanning stability. They call the local API, so start the backend first:

```bash
python scripts/verify_capacity.py
python scripts/verify_lateness.py
python scripts/verify_replan_stable.py
```

## Project status

This is an active portfolio project. It demonstrates capacity-aware monthly planning, schedule comparison, manual sequencing, and material requirements across a multi-team route.

## License

No license has been added yet.
