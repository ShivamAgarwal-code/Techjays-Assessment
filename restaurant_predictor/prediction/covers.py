"""Covers prediction engine.

Predicts daily and hourly customer counts using multiplicative factors
loaded from the coefficients table.
"""

from datetime import date, timedelta

from ..db import load_coefficients, get_recent_daily_totals
from ..config import OPERATING_HOURS
from ..models import CoverPrediction


def compute_trend_factor(conn, target_date):
    """Compute a linear trend factor from recent historical data.

    Compares average daily covers from the last 30 days vs days 60-90 ago.
    Clamped to [0.85, 1.15] to prevent extreme swings.
    """
    daily_totals = get_recent_daily_totals(conn, target_date.isoformat(), days=90)
    if len(daily_totals) < 60:
        return 1.0

    recent = [d['daily_total'] for d in daily_totals[:30]]
    older = [d['daily_total'] for d in daily_totals[60:90]]

    if not recent or not older:
        return 1.0

    recent_avg = sum(recent) / len(recent)
    older_avg = sum(older) / len(older)

    if older_avg == 0:
        return 1.0

    trend = recent_avg / older_avg
    return max(0.85, min(1.15, trend))


def predict_covers(conn, target_date, weather='clear', event=None):
    """Predict daily and hourly covers for a target date.

    Formula: daily = base * dow_factor * month_factor * weather_factor * event_factor * trend
    Hourly: hourly[h] = daily * hour_share[h]
    """
    coeffs = load_coefficients(conn)

    base = coeffs.get('base_daily', {}).get('default', 150)
    dow = coeffs.get('dow_factor', {}).get(str(target_date.weekday()), 1.0)
    month = coeffs.get('month_factor', {}).get(str(target_date.month), 1.0)
    w = coeffs.get('weather_factor', {}).get(weather, 1.0)
    e = coeffs.get('event_factor', {}).get(event, 1.0) if event else 1.0

    trend = compute_trend_factor(conn, target_date)

    daily_total = base * dow * month * w * e * trend

    # Compute hourly breakdown
    hourly = {}
    hour_shares = coeffs.get('hour_share', {})
    for h in OPERATING_HOURS:
        share = hour_shares.get(str(h), 1.0 / len(OPERATING_HOURS))
        hourly[h] = max(0, round(daily_total * share))

    # Adjust rounding so sum matches daily total
    _adjust_rounding(hourly, round(daily_total))

    return CoverPrediction(
        target_date=target_date,
        daily_total=round(daily_total),
        hourly=hourly,
        weather=weather,
        event=event,
        trend_factor=trend,
    )


def _adjust_rounding(hourly, target_total):
    """Adjust hourly values so they sum to the daily total."""
    current_sum = sum(hourly.values())
    diff = target_total - current_sum

    if diff == 0:
        return

    # Distribute the difference across hours proportionally
    sorted_hours = sorted(hourly.keys(), key=lambda h: hourly[h], reverse=True)
    step = 1 if diff > 0 else -1

    for i in range(abs(diff)):
        h = sorted_hours[i % len(sorted_hours)]
        hourly[h] = max(0, hourly[h] + step)
