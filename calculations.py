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

    Capacity- and calendar-aware delivery date planning is handled
    separately by the weekly batch planning run (see planning.py), since
    the spec treats material requirements and delivery-date scheduling as
    distinct steps: registering an order computes requirements immediately,
    while delivery dates are only computed when the monthly planning run
    executes across all of that month's orders together.
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

    output_needed = float(order.quantity_requested)
    results = []

    for team in teams_in_chain:
        efficiency = float(team.efficiency)

        if efficiency <= 0:
            results.append({
                "team_id": team.id,
                "team_name": team.name,
                "sequence_order": team.sequence_order,
                "output_needed": round(output_needed, 2),
                "input_needed": None,
                "efficiency": efficiency,
                "monthly_capacity": float(team.monthly_capacity),
                "weekly_capacity": team.weekly_capacity,
                "error": f"Team '{team.name}' has zero or invalid efficiency -- cannot compute requirement",
            })
            break

        input_needed = output_needed / efficiency

        results.append({
            "team_id": team.id,
            "team_name": team.name,
            "sequence_order": team.sequence_order,
            "output_needed": round(output_needed, 2),
            "input_needed": round(input_needed, 2),
            "efficiency": efficiency,
            "monthly_capacity": float(team.monthly_capacity),
            "weekly_capacity": team.weekly_capacity,
        })

        output_needed = input_needed

    return {
        "order_id": order.id,
        "customer_name": order.customer_name,
        "quantity_requested": float(order.quantity_requested),
        "entry_team": entry_team.name,
        "requested_delivery_date": str(order.requested_delivery_date) if order.requested_delivery_date else None,
        "calculated_delivery_date": str(order.calculated_delivery_date) if order.calculated_delivery_date else None,
        "total_raw_material_needed": round(output_needed, 2),
        "steps": results,
    }