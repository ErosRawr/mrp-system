"""
Order-prioritization heuristics for comparing planning strategies.

Three criteria, each producing a different ORDER in which orders are
scheduled (earlier in the list = scheduled first = gets capacity first):

    peps          -- pure FIFO by requested_delivery_date (ties by order id)
    prioritario   -- priority orders first (by date), then the rest (by date)
    heuristica    -- priority first, then tonnage (15k+ ranks continuously,
                     below 15k ties and falls through to tipo_pedido rank),
                     then tipo_pedido rank (comercial highest, especial lowest)
"""

TONNAGE_THRESHOLD = 15000  # tons -- at/above this, orders rank continuously
                            # by tonnage; below this, tonnage doesn't
                            # differentiate orders at all (falls through
                            # to the next tiebreaker)

# Highest priority first. Any tipo_pedido not in this list ranks below
# everything here (unknown/unspecified types sort last).
TIPO_PEDIDO_RANK = [
    "comercial",
    "galvanizado",
    "perfiles",
    "perfileros",
    "tuberia",
    "ojalatero",
    "especial",
]


def _tipo_pedido_rank(tipo_pedido):
    """Lower number = higher priority. Unknown/None types sort last."""
    if tipo_pedido is None:
        return len(TIPO_PEDIDO_RANK)
    normalized = tipo_pedido.strip().lower()
    try:
        return TIPO_PEDIDO_RANK.index(normalized)
    except ValueError:
        return len(TIPO_PEDIDO_RANK)


def sort_orders_peps(orders):
    """Pure FIFO: earliest requested_delivery_date first. Orders with no
    requested date sort last. Ties broken by order id for determinism."""
    return sorted(
        orders,
        key=lambda o: (
            o.requested_delivery_date is None,
            o.requested_delivery_date or o.order_date,
            o.id,
        ),
    )


def sort_orders_prioritario(orders):
    """Priority orders first (as a group, sorted by date within), then
    every non-priority order (sorted by date within)."""
    return sorted(
        orders,
        key=lambda o: (
            0 if o.is_priority else 1,
            o.requested_delivery_date is None,
            o.requested_delivery_date or o.order_date,
            o.id,
        ),
    )


def sort_orders_heuristica(orders):
    """
    Three-level sort:
      1. Priority orders first.
      2. Tonnage: orders at/above TONNAGE_THRESHOLD rank continuously by
         tonnage (descending -- biggest first). Orders below the
         threshold are all treated as equal on this axis and fall
         through to the next tiebreaker.
      3. tipo_pedido rank (comercial highest, especial lowest, unknown last).
      4. requested_delivery_date, then order id, as final tiebreakers.
    """
    def sort_key(o):
        qty = float(o.quantity_requested)
        above_threshold = qty >= TONNAGE_THRESHOLD
        # Negative tonnage for descending order within the "above
        # threshold" tier; orders below threshold all get the same
        # tonnage-tier value (0) so they tie and fall through.
        tonnage_tier = -qty if above_threshold else 0

        return (
            0 if o.is_priority else 1,
            tonnage_tier,
            _tipo_pedido_rank(o.tipo_pedido),
            o.requested_delivery_date is None,
            o.requested_delivery_date or o.order_date,
            o.id,
        )

    return sorted(orders, key=sort_key)


CRITERIA = {
    "peps": sort_orders_peps,
    "prioritario": sort_orders_prioritario,
    "heuristica": sort_orders_heuristica,
}


def sort_orders_by_criterion(orders, criterion: str):
    sorter = CRITERIA.get(criterion)
    if sorter is None:
        raise ValueError(f"Unknown criterion '{criterion}'. Valid options: {list(CRITERIA.keys())}")
    return sorter(orders)
