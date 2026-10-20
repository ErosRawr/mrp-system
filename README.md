# MRP System

> Turn scattered production orders into a clear, capacity-aware plan across every team in the process.

MRP System is a manufacturing planning application built around a multi-team production route. Define teams and their capacity, enter customer orders, calculate material requirements, and schedule production to estimate delivery dates and workload.

## Features

- Configure production teams with sequence, monthly capacity, weekly availability, efficiency, and holiday staffing.
- Create, update, and delete customer orders with requested delivery dates, priority, and order type.
- Calculate material input requirements across the production route.
- Plan orders against weekly team capacity and estimate delivery dates.
- Compare three planning criteria before committing a plan:
  - **PEPS (FIFO):** earliest requested delivery date first.
  - **Prioritario:** priority orders first, then requested delivery date.
  - **Heurística:** priority first, followed by large orders (15,000+ tons), order type, and requested delivery date.
- Track weekly capacity exceptions, import Mexican holiday impacts, and generate reproducible capacity disruptions through the API.
- Review order lateness, team occupancy, availability calendars, and capacity allocations.

## Planning workflow

1. Create teams in production sequence and set their capacity and efficiency.
2. Add customer orders, including quantity, entry team, and requested delivery date.
3. Review material requirements for an order.
4. Compare scheduling criteria for a month.
5. Run the selected plan and review delivery dates, lateness, and team occupancy.

The current planner compares predefined scheduling criteria. **Rearranging planning blocks and filtering orders are planned improvements** and are not available in the current interface.

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

To load the optional demo dataset, install its HTTP client too:

```bash
pip install requests
```

### 2. Start the API

From the repository root:

```bash
uvicorn main:app --reload
```

The API is available at [http://localhost:8000](http://localhost:8000). Interactive endpoint documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).

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
python seed_data.py
```

The script creates a sample production route and orders for 2026, imports Mexican holiday impacts, generates seeded capacity disruptions, and plans the other months. It leaves September unplanned so you can compare the scheduling criteria and run the selected plan as a demo. Run it once against a fresh database to avoid duplicate sample records.

## Project structure

```text
.
├── frontend/
│   ├── css/                 # Interface styles
│   ├── js/                  # Dashboard and planning interface
│   └── index.html           # Main browser app
├── calculations.py          # Material requirement calculations
├── capacity.py              # Capacity calculations
├── database.py              # SQLite connection and SQLAlchemy sessions
├── disruptions.py           # Reproducible disruption generation
├── heuristics.py            # Planning order criteria
├── lateness.py              # Delivery lateness classification
├── main.py                  # FastAPI application and endpoints
├── mexican_holidays.py      # Mexican holiday calendar calculations
├── models.py                # SQLAlchemy data models
├── planning.py              # Monthly planning and replanning
├── seed_data.py             # Optional demo data loader
├── verify_capacity.py       # Capacity verification script
├── verify_lateness.py       # Lateness verification script
├── verify_replan_stable.py  # Replanning stability check
└── requirements.txt         # Backend dependencies
```

## Verification scripts

The repository includes scripts for checking capacity allocations, lateness reporting, and replanning stability. They call the local API, so start the backend first. The scripts also require the `requests` package:

```bash
python verify_capacity.py
python verify_lateness.py
python verify_replan_stable.py
```

## Project status

This is an active portfolio project. The current application demonstrates capacity-aware monthly planning and schedule comparison. A block-oriented planning experience—with order filtering and rearrangeable planning blocks—is planned next.

## License

No license has been added yet.
