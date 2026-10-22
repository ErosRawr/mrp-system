"""
Random productivity drops ("interrupciones"): unplanned downtime, equipment
trouble, a short-staffed week. Any team has a `probability` chance of a drop
in any given ISO week; the size of each drop is drawn between `min_drop` and
`max_drop` (as a share of that week's capacity).

The draws only DECIDE which team-weeks are hit. The caller stores them as
ordinary TeamWeekException rows, so the planner, the calendar and the
occupancy view all see them like any other availability change -- and a plan
is never random: it is computed from stored, visible exceptions.
"""

import random

DEFAULT_PROBABILITY = 0.10   # 10% chance per team per week
DEFAULT_MIN_DROP = 0.10      # a hit removes at least 10% of that week's capacity
DEFAULT_MAX_DROP = 0.40      # ... and at most 40%


def draw_disruptions(team_ids, probability=DEFAULT_PROBABILITY,
                     min_drop=DEFAULT_MIN_DROP, max_drop=DEFAULT_MAX_DROP,
                     seed=None, weeks=52):
    """
    Returns a list of (team_id, week_number, drop) for the team-weeks that
    were hit, `drop` being the share of capacity lost (0.25 = 25%).

    Both random numbers are drawn for every team-week whether or not it is
    hit, so a given seed always picks the same weeks even if `probability`
    is changed afterwards. seed=None uses fresh randomness each call.
    """
    rng = random.Random(seed)
    hits = []
    for team_id in team_ids:
        for week in range(1, weeks + 1):
            is_hit = rng.random() < probability
            drop = round(rng.uniform(min_drop, max_drop), 2)
            if is_hit:
                hits.append((team_id, week, drop))
    return hits
