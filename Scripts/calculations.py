from sqlalchemy.orm import Session
import models


def calculate_material_requirements(order_id: int, db: Session):
    """
    Walks backward from an order's entry team through team #1, computing
    how much material each team must produce to net the requested tonnage
    at the entry team, based on each team's efficiency ("rendimiento").

    This is PURELY the material calculation -- no dates, no capacity, no
    scheduling. Given the current team chain and their efficiencies, it
    answers: "how much must each upstream team produce?"

    Note: only teams with sequence_order <= the order's entry team are
    included -- e.g. an order entering at team #2 of 4 will correctly
    show only teams #1 and #2, not all four. This is intentional: teams
    downstream of the entry point are not part of that order's route.

    Each step also reports its `loss` (input minus output: what that team
    scraps), and the result carries `total_loss` and `overall_yield`
    (finished tons / raw tons). If a team has an unusable efficiency, `error`
    says so and the totals are None rather than a misleading partial number.
    """
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        return None

    entry_team = (
        db.query(models.Team)
        .filter(models.Team.id == order.entry_team_id)
        .first()
    )
    if not entry_team:
        return None

    teams_in_chain = (
        db.query(models.Team)
        .filter(models.Team.sequence_order <= entry_team.sequence_order)
        .order_by(models.Team.sequence_order.desc())
        .all()
    )

    finished = float(order.quantity_requested)
    output_needed = finished
    results = []
    error = None

    for team in teams_in_chain:
        efficiency = float(team.efficiency)

        if efficiency <= 0:
            error = f"Team '{team.name}' has zero or invalid efficiency -- cannot compute requirement"
            results.append({
                "team_id": team.id,
                "team_name": team.name,
                "sequence_order": team.sequence_order,
                "output_needed": round(output_needed, 2),
                "input_needed": None,
                "loss": None,
                "efficiency": efficiency,
                "monthly_capacity": float(team.monthly_capacity),
                "weekly_capacity": team.weekly_capacity,
                "error": error,
            })
            break

        input_needed = output_needed / efficiency

        results.append({
            "team_id": team.id,
            "team_name": team.name,
            "sequence_order": team.sequence_order,
            "output_needed": round(output_needed, 2),
            "input_needed": round(input_needed, 2),
            "loss": round(input_needed - output_needed, 2),
            "efficiency": efficiency,
            "monthly_capacity": float(team.monthly_capacity),
            "weekly_capacity": team.weekly_capacity,
        })

        output_needed = input_needed

    raw = None if error else output_needed
    return {
        "order_id": order.id,
        "customer_name": order.customer_name,
        "quantity_requested": float(order.quantity_requested),
        "entry_team": entry_team.name,
        "requested_delivery_date": str(order.requested_delivery_date) if order.requested_delivery_date else None,
        "calculated_delivery_date": str(order.calculated_delivery_date) if order.calculated_delivery_date else None,
        "total_raw_material_needed": None if raw is None else round(raw, 2),
        "total_loss": None if raw is None else round(raw - finished, 2),
        "overall_yield": None if raw is None else round(finished / raw, 4),
        "error": error,
        "steps": results,
    }


def monthly_requirements(year: int, month: int, db: Session):
    """
    The material requirement of every order planned for (year, month), added up:
    totals for the month, one line per order, and what each team has to
    process. Pure material, like the single-order calculation -- the only
    comparison made is each team's tons to produce against its monthly capacity.
    """
    orders = (
        db.query(models.Order)
        .filter(models.Order.planning_year == year, models.Order.planning_month == month)
        .order_by(models.Order.order_date, models.Order.id)
        .all()
    )

    teams = {
        t.id: {
            "team_id": t.id,
            "team_name": t.name,
            "sequence_order": t.sequence_order,
            "efficiency": float(t.efficiency),
            "monthly_capacity": float(t.monthly_capacity),
            "orders": 0,
            "output_needed": 0.0,
            "input_needed": 0.0,
        }
        for t in db.query(models.Team).order_by(models.Team.sequence_order).all()
    }

    per_order, errors = [], []
    finished_total = raw_total = 0.0

    for order in orders:
        req = calculate_material_requirements(order.id, db)
        if req is None or req["error"]:
            errors.append({
                "order_id": order.id,
                "customer_name": order.customer_name,
                "error": (req or {}).get("error") or "Could not calculate material requirements for this order",
            })
            continue

        per_order.append({
            "order_id": req["order_id"],
            "customer_name": req["customer_name"],
            "entry_team": req["entry_team"],
            "quantity_requested": req["quantity_requested"],
            "total_raw_material_needed": req["total_raw_material_needed"],
            "total_loss": req["total_loss"],
            "overall_yield": req["overall_yield"],
        })
        finished_total += req["quantity_requested"]
        raw_total += req["total_raw_material_needed"]

        for step in req["steps"]:
            team = teams[step["team_id"]]
            team["orders"] += 1
            team["output_needed"] += step["output_needed"]
            team["input_needed"] += step["input_needed"]

    team_rows = []
    for team in teams.values():
        capacity = team["monthly_capacity"]
        team_rows.append({
            **team,
            "output_needed": round(team["output_needed"], 2),
            "input_needed": round(team["input_needed"], 2),
            "loss": round(team["input_needed"] - team["output_needed"], 2),
            "load_pct": round(team["output_needed"] / capacity * 100, 1) if capacity > 0 else None,
        })

    return {
        "planning_year": year,
        "planning_month": month,
        "orders_count": len(per_order),
        "totals": {
            "finished": round(finished_total, 2),
            "raw": round(raw_total, 2),
            "loss": round(raw_total - finished_total, 2),
            "overall_yield": round(finished_total / raw_total, 4) if raw_total > 0 else None,
        },
        "teams": team_rows,
        "orders": per_order,
        "errors": errors,
    }
