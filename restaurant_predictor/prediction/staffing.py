"""Staff scheduling engine.

Converts hourly cover predictions into staff requirements by role and station,
with shift smoothing and labor cost estimation.
"""

import math

from ..db import get_all_staff_roles
from ..config import OPERATING_HOURS, MIN_SHIFT_HOURS
from ..models import StaffAssignment, StaffSchedule


def predict_staffing(conn, cover_prediction):
    """Generate a staff schedule from cover predictions.

    For each hour and role/station: staff = ceil(covers / covers_per_staff),
    clamped to [min_on_shift, max_on_shift]. Then smoothed with minimum
    4-hour shift blocks.
    """
    roles = get_all_staff_roles(conn)
    hourly_covers = cover_prediction.hourly

    # Step 1: Compute raw staff needs per hour per role
    raw_schedule = {}  # {(role, station): {hour: count}}
    for role in roles:
        key = (role['role'], role['station'])
        raw_schedule[key] = {}
        for hour in OPERATING_HOURS:
            covers = hourly_covers.get(hour, 0)
            if covers == 0:
                raw_need = role['min_on_shift']
            else:
                raw_need = math.ceil(covers / role['covers_per_staff'])
            clamped = max(role['min_on_shift'], min(role['max_on_shift'], raw_need))
            raw_schedule[key][hour] = clamped

    # Step 2: Apply shift smoothing (min 4-hour blocks)
    smoothed = _smooth_shifts(raw_schedule)

    # Step 3: Build assignment list and compute cost
    assignments = []
    total_cost = 0.0
    rate_lookup = {(r['role'], r['station']): r['hourly_rate'] for r in roles}

    for (role, station), hour_counts in smoothed.items():
        rate = rate_lookup.get((role, station), 0)
        for hour in OPERATING_HOURS:
            count = hour_counts.get(hour, 0)
            assignments.append(StaffAssignment(
                hour=hour,
                role=role,
                station=station,
                staff_count=count,
                covers=hourly_covers.get(hour, 0),
            ))
            total_cost += count * rate

    return StaffSchedule(
        target_date=cover_prediction.target_date,
        assignments=assignments,
        total_labor_cost=total_cost,
    )


def _smooth_shifts(raw_schedule):
    """Apply minimum shift-block smoothing.

    Within each MIN_SHIFT_HOURS window, set all hours to the window's max
    to avoid calling staff in for single-hour stints.
    """
    smoothed = {}
    for key, hour_counts in raw_schedule.items():
        hours = sorted(hour_counts.keys())
        new_counts = dict(hour_counts)

        for i in range(len(hours)):
            window_end = min(i + MIN_SHIFT_HOURS, len(hours))
            window_hours = hours[i:window_end]
            block_max = max(hour_counts[h] for h in window_hours)
            for h in window_hours:
                new_counts[h] = max(new_counts[h], block_max)

        smoothed[key] = new_counts

    return smoothed
