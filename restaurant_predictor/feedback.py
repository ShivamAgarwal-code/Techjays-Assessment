"""Feedback loop: correction ingestion and coefficient updates.

Uses exponential smoothing with adaptive alpha to adjust prediction
coefficients based on manager corrections. The system learns from
its mistakes and converges toward accuracy over time.
"""

from datetime import date

from .db import (
    get_coefficient, save_coefficient, save_correction,
    load_coefficients, get_recent_daily_totals, get_historical_covers,
)
from .config import BASE_ALPHA, WEATHER_REASONS, EVENT_NAMES, OPERATING_HOURS
from .prediction.covers import predict_covers


def adaptive_alpha(base_alpha, update_count):
    """Compute learning rate based on how many corrections this coefficient has seen.

    Early corrections are aggressive (learn fast from initial errors).
    Later corrections are conservative (fine-tuning).
    """
    if update_count < 5:
        return min(base_alpha * 2, 0.40)
    elif update_count < 20:
        return base_alpha
    else:
        return max(base_alpha * 0.5, 0.05)


def _update_coefficient(conn, coeff_type, coeff_key, error_ratio, weight=1.0):
    """Update a single coefficient using weighted exponential smoothing.

    Returns (old_value, new_value, alpha_used) for reporting.
    """
    row = get_coefficient(conn, coeff_type, coeff_key)
    if row is None:
        return None

    current_val = row['value']
    update_count = row['update_count']

    # Weighted error ratio: partially pull toward the implied correction
    weighted_error_ratio = 1.0 + weight * (error_ratio - 1.0)
    implied_coeff = current_val * weighted_error_ratio

    alpha = adaptive_alpha(BASE_ALPHA, update_count)
    new_val = alpha * implied_coeff + (1 - alpha) * current_val

    save_coefficient(conn, coeff_type, coeff_key, new_val, update_count + 1)

    return {
        'coeff_type': coeff_type,
        'coeff_key': coeff_key,
        'old_value': current_val,
        'new_value': new_val,
        'alpha': alpha,
        'update_count': update_count + 1,
    }


def apply_correction(conn, target_date, predicted, actual, hour=None, reason=None):
    """Apply a manager correction and update relevant coefficients.

    Attribution logic:
    - If reason is a weather type → update weather_factor for that type
    - If reason is an event name → update event_factor for that event
    - Otherwise → split error across dow_factor (70%) and base_daily (30%)

    Returns a dict with correction details and coefficient updates.
    """
    if predicted == 0:
        predicted = 1  # avoid division by zero

    error_ratio = actual / predicted
    coefficients_updated = []

    if reason and reason in WEATHER_REASONS:
        result = _update_coefficient(conn, 'weather_factor', reason, error_ratio, weight=1.0)
        if result:
            coefficients_updated.append(result)
    elif reason and reason in EVENT_NAMES:
        result = _update_coefficient(conn, 'event_factor', reason, error_ratio, weight=1.0)
        if result:
            coefficients_updated.append(result)
    else:
        # Distribute error across day-of-week and base
        dow = str(target_date.weekday())
        result_dow = _update_coefficient(conn, 'dow_factor', dow, error_ratio, weight=0.70)
        if result_dow:
            coefficients_updated.append(result_dow)

        result_base = _update_coefficient(conn, 'base_daily', 'default', error_ratio, weight=0.30)
        if result_base:
            coefficients_updated.append(result_base)

    # If hourly correction, also update hour_share
    if hour is not None:
        # We need daily actual to compute the share
        daily_actual = actual  # In hourly mode, we treat this differently
        # For hourly corrections, update the hour_share
        coeffs = load_coefficients(conn)
        current_share = coeffs.get('hour_share', {}).get(str(hour), 0.08)

        # We can't perfectly compute implied share without knowing total daily actual,
        # but we can adjust proportionally
        if predicted > 0:
            hourly_error = actual / predicted
            result_hour = _update_coefficient(conn, 'hour_share', str(hour), hourly_error, weight=0.5)
            if result_hour:
                coefficients_updated.append(result_hour)
                _renormalize_hour_shares(conn)

    # Record the correction
    save_correction(
        conn, target_date.isoformat(), hour, predicted, actual, reason,
        [{'type': c['coeff_type'], 'key': c['coeff_key'],
          'old': round(c['old_value'], 4), 'new': round(c['new_value'], 4)}
         for c in coefficients_updated]
    )

    return {
        'date': target_date,
        'predicted': predicted,
        'actual': actual,
        'error_ratio': error_ratio,
        'reason': reason,
        'coefficients_updated': coefficients_updated,
    }


def _renormalize_hour_shares(conn):
    """Renormalize hour_share coefficients to sum to 1.0."""
    coeffs = load_coefficients(conn)
    hour_shares = coeffs.get('hour_share', {})

    total = sum(hour_shares.values())
    if total == 0:
        return

    for hour_str, val in hour_shares.items():
        row = get_coefficient(conn, 'hour_share', hour_str)
        if row:
            save_coefficient(conn, 'hour_share', hour_str,
                             val / total, row['update_count'])


def batch_train(conn, days=30):
    """Replay historical data as corrections to train coefficients toward true values.

    Fetches the most recent N days of historical data, runs predictions
    against each, and applies corrections for the difference.

    Returns a summary of the training run.
    """
    from datetime import date as date_cls

    daily_totals = get_recent_daily_totals(conn, '9999-12-31', days=days)
    if not daily_totals:
        return {'days_trained': 0, 'message': 'No historical data found.'}

    corrections_applied = 0
    total_error_before = 0.0
    total_error_after = 0.0

    for day_data in daily_totals:
        d = date_cls.fromisoformat(day_data['date'])
        actual_daily = day_data['daily_total']
        weather = day_data['weather'] or 'clear'

        # Look up event from historical data
        event_row = conn.execute(
            "SELECT event_name FROM historical_covers WHERE date=? AND event_name IS NOT NULL LIMIT 1",
            (day_data['date'],)
        ).fetchone()
        event = event_row['event_name'] if event_row else None

        # Predict with current coefficients
        prediction = predict_covers(conn, d, weather=weather, event=event)
        predicted_daily = prediction.daily_total

        if predicted_daily == 0:
            continue

        error_before = abs(predicted_daily - actual_daily) / actual_daily
        total_error_before += error_before

        # Apply correction if error is significant (>2%)
        if abs(predicted_daily - actual_daily) > actual_daily * 0.02:
            # Determine reason for attribution
            reason = None
            if weather != 'clear':
                reason = weather
            elif event:
                reason = event

            apply_correction(conn, d, predicted_daily, actual_daily, reason=reason)
            corrections_applied += 1

            # For clear-weather, no-event days, also nudge month_factor
            if weather == 'clear' and event is None:
                error_ratio = actual_daily / predicted_daily
                _update_coefficient(conn, 'month_factor', str(d.month), error_ratio, weight=0.3)

        # Train hourly shares using actual hourly data
        actual_hourly = get_historical_covers(conn, day_data['date'])
        if actual_hourly and actual_daily > 0:
            for hour_str_h, actual_h_covers in actual_hourly.items():
                actual_share = actual_h_covers / actual_daily
                current_share_val = load_coefficients(conn).get('hour_share', {}).get(str(hour_str_h), 0.08)
                if current_share_val > 0:
                    share_ratio = actual_share / current_share_val
                    _update_coefficient(conn, 'hour_share', str(hour_str_h), share_ratio, weight=0.3)
            _renormalize_hour_shares(conn)

        # Re-predict after correction
        prediction_after = predict_covers(conn, d, weather=weather, event=event)
        error_after = abs(prediction_after.daily_total - actual_daily) / actual_daily
        total_error_after += error_after

    n = len(daily_totals)
    avg_error_before = (total_error_before / n * 100) if n > 0 else 0
    avg_error_after = (total_error_after / n * 100) if n > 0 else 0

    return {
        'days_trained': n,
        'corrections_applied': corrections_applied,
        'avg_error_before': round(avg_error_before, 1),
        'avg_error_after': round(avg_error_after, 1),
    }
