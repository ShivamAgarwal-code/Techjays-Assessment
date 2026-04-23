"""CLI interface for the restaurant prediction system."""

import click
import json
from datetime import date, datetime
from pathlib import Path

from .db import (
    get_connection, init_db, load_coefficients, save_prediction,
    get_corrections_history, get_predictions_history, get_coefficient,
)
from .synthetic import generate_synthetic_data
from .prediction.covers import predict_covers
from .prediction.staffing import predict_staffing
from .prediction.ingredients import predict_ingredients
from .feedback import apply_correction, batch_train
from .config import OPERATING_HOURS, WEATHER_REASONS, EVENT_NAMES

DEFAULT_DB = str(Path(__file__).parent.parent / 'data' / 'restaurant.db')

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


@click.group()
def cli():
    """Restaurant Resource Prediction System.

    Predicts covers, staff scheduling, and ingredient orders for any date.
    Accepts corrections from managers and adjusts predictions over time.
    """
    pass


@cli.command()
@click.option('--db-path', default=DEFAULT_DB, help='Path to SQLite database.')
@click.option('--seed', default=42, help='Random seed for data generation.')
@click.option('--days', default=730, help='Number of days of historical data.')
def init(db_path, seed, days):
    """Initialize the database with synthetic data."""
    db_path_obj = Path(db_path)
    if db_path_obj.exists():
        db_path_obj.unlink()
        click.echo(f"Removed existing database at {db_path}")

    conn = get_connection(db_path)
    click.echo(f"Generating {days} days of synthetic data (seed={seed})...")
    generate_synthetic_data(conn, seed=seed, num_days=days)
    conn.close()

    click.echo(f"Database initialized at {db_path}")
    click.echo(f"  - {days} days of historical covers")
    click.echo(f"  - 20 menu items with recipes")
    click.echo(f"  - 37 ingredients with shelf life / lead times")
    click.echo(f"  - 8 staff role/station configurations")
    click.echo(f"  - Coefficients seeded with deliberately inaccurate initial values")
    click.echo(f"\nRun 'predict' to generate predictions, 'correct' to submit feedback.")


@cli.command()
@click.argument('target_date')
@click.option('--weather', default='clear', type=click.Choice(['clear', 'rain', 'snow', 'extreme_heat']))
@click.option('--event', default=None, help=f'Event name: {", ".join(sorted(EVENT_NAMES))}')
@click.option('--db-path', default=DEFAULT_DB)
def predict(target_date, weather, event, db_path):
    """Predict covers, staff, and ingredients for a date (YYYY-MM-DD)."""
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        click.echo("Error: Date must be in YYYY-MM-DD format.", err=True)
        return

    conn = get_connection(db_path)

    # --- Covers ---
    cover_pred = predict_covers(conn, d, weather=weather, event=event)

    click.echo(f"\n{'='*60}")
    click.echo(f"  Prediction for {target_date} ({DAY_NAMES[d.weekday()]})")
    click.echo(f"{'='*60}")
    click.echo(f"  Weather: {weather} | Event: {event or 'none'} | Trend: {cover_pred.trend_factor:.3f}")
    click.echo()

    # Hourly covers table
    click.echo("  --- Hourly Covers ---")
    click.echo(f"  {'Hour':<8} {'Covers':>8}")
    click.echo(f"  {'-'*16}")
    for h in OPERATING_HOURS:
        click.echo(f"  {h:02d}:00   {cover_pred.hourly.get(h, 0):>8}")
    click.echo(f"  {'-'*16}")
    click.echo(f"  {'TOTAL':<8} {cover_pred.daily_total:>8}")

    # Save prediction
    save_prediction(conn, target_date, cover_pred.hourly)

    # --- Staff Schedule ---
    staff = predict_staffing(conn, cover_pred)

    click.echo(f"\n  --- Staff Schedule ---")

    # Build a table: hours as rows, roles as columns
    roles_seen = []
    role_labels = []
    for a in staff.assignments:
        key = (a.role, a.station)
        if key not in roles_seen:
            roles_seen.append(key)
            label = f"{a.role}" if not a.station else f"{a.role}({a.station})"
            role_labels.append(label)

    # Header
    col_width = max(len(l) for l in role_labels) + 1 if role_labels else 10
    col_width = max(col_width, 6)
    header = f"  {'Hour':<8}" + "".join(f"{l:>{col_width}}" for l in role_labels)
    click.echo(header)
    click.echo(f"  {'-' * (8 + col_width * len(role_labels))}")

    # Build lookup
    staff_lookup = {}
    for a in staff.assignments:
        staff_lookup[(a.hour, a.role, a.station)] = a.staff_count

    for h in OPERATING_HOURS:
        row = f"  {h:02d}:00   "
        for (role, station) in roles_seen:
            count = staff_lookup.get((h, role, station), 0)
            row += f"{count:>{col_width}}"
        click.echo(row)

    click.echo(f"\n  Est. labor cost: ${staff.total_labor_cost:,.2f}")

    # --- Ingredients ---
    ingredient_orders = predict_ingredients(conn, cover_pred)

    click.echo(f"\n  --- Ingredient Orders ---")
    click.echo(f"  {'Ingredient':<22} {'Qty':>10} {'Unit':<6} {'Order By':<12} {'Delivery':<12} {'Cost':>10}")
    click.echo(f"  {'-'*72}")

    total_ingredient_cost = 0.0
    for order in ingredient_orders:
        total_ingredient_cost += order.estimated_cost
        click.echo(
            f"  {order.ingredient_name:<22} "
            f"{order.quantity:>10,.0f} "
            f"{order.unit:<6} "
            f"{order.order_date.isoformat():<12} "
            f"{order.delivery_date.isoformat():<12} "
            f"${order.estimated_cost:>9,.2f}"
        )

    click.echo(f"  {'-'*72}")
    click.echo(f"  Est. ingredient cost: ${total_ingredient_cost:,.2f}")
    click.echo()

    conn.close()


@cli.command()
@click.argument('target_date')
@click.option('--predicted', required=True, type=float, help='Predicted cover count.')
@click.option('--actual', required=True, type=float, help='Actual cover count.')
@click.option('--hour', default=None, type=int, help='Specific hour (for hourly correction).')
@click.option('--reason', default=None, help='Reason for discrepancy (rain, snow, event name, etc.).')
@click.option('--db-path', default=DEFAULT_DB)
def correct(target_date, predicted, actual, hour, reason, db_path):
    """Submit a correction for a past prediction."""
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        click.echo("Error: Date must be in YYYY-MM-DD format.", err=True)
        return

    conn = get_connection(db_path)

    result = apply_correction(conn, d, predicted, actual, hour=hour, reason=reason)

    click.echo(f"\n  Correction recorded for {target_date}.")
    click.echo(f"  Error ratio: {result['error_ratio']:.3f} (predicted {int(predicted)}, actual {int(actual)})")

    if reason:
        click.echo(f"  Reason: {reason}")

    click.echo(f"\n  Coefficient updates:")
    for update in result['coefficients_updated']:
        click.echo(
            f"    {update['coeff_type']}['{update['coeff_key']}']: "
            f"{update['old_value']:.4f} -> {update['new_value']:.4f}  "
            f"(alpha={update['alpha']:.2f}, update #{update['update_count']})"
        )

    # Re-run prediction to show the effect
    weather = reason if reason in WEATHER_REASONS else 'clear'
    event = reason if reason in EVENT_NAMES else None
    new_pred = predict_covers(conn, d, weather=weather, event=event)
    click.echo(f"\n  Re-prediction with updated coefficients: {new_pred.daily_total} covers")
    click.echo()

    conn.close()


@cli.command('show-coefficients')
@click.option('--type', 'coeff_type', default=None, help='Filter by coefficient type.')
@click.option('--db-path', default=DEFAULT_DB)
def show_coefficients(coeff_type, db_path):
    """Display current prediction coefficients."""
    conn = get_connection(db_path)
    coeffs = load_coefficients(conn)

    click.echo(f"\n  {'='*50}")
    click.echo(f"  Current Prediction Coefficients")
    click.echo(f"  {'='*50}")

    type_labels = {
        'base_daily': 'Base Daily Covers',
        'dow_factor': 'Day-of-Week Factors',
        'month_factor': 'Monthly Factors',
        'hour_share': 'Hourly Distribution',
        'weather_factor': 'Weather Factors',
        'event_factor': 'Event Factors',
    }

    dow_labels = dict(enumerate(DAY_NAMES))

    for ct, values in sorted(coeffs.items()):
        if coeff_type and ct != coeff_type:
            continue

        label = type_labels.get(ct, ct)
        click.echo(f"\n  --- {label} ---")

        for key in sorted(values.keys(), key=lambda k: (k.isdigit(), int(k) if k.isdigit() else 0, k)):
            val = values[key]
            row = get_coefficient(conn, ct, key)
            count = row['update_count'] if row else 0

            # Pretty labels
            if ct == 'dow_factor':
                display_key = dow_labels.get(int(key), key)
            elif ct == 'month_factor':
                display_key = MONTH_NAMES[int(key)] if key.isdigit() and 1 <= int(key) <= 12 else key
            elif ct == 'hour_share':
                display_key = f"{int(key):02d}:00"
            else:
                display_key = key

            click.echo(f"    {display_key:<16} {val:>8.4f}  (updates: {count})")

    click.echo()
    conn.close()


@cli.command()
@click.option('--last', default=20, help='Number of recent entries.')
@click.option('--db-path', default=DEFAULT_DB)
def history(last, db_path):
    """Show past predictions and corrections."""
    conn = get_connection(db_path)

    # Corrections
    corrections = get_corrections_history(conn, limit=last)
    click.echo(f"\n  --- Recent Corrections ({len(corrections)}) ---")
    click.echo(f"  {'Date':<12} {'Hour':<6} {'Predicted':>10} {'Actual':>10} {'Reason':<16} {'Applied At'}")
    click.echo(f"  {'-'*70}")
    for c in corrections:
        hour_str = f"{c['hour']:02d}:00" if c['hour'] is not None else "all"
        click.echo(
            f"  {c['date']:<12} {hour_str:<6} "
            f"{c['predicted_value']:>10.0f} {c['actual_value']:>10.0f} "
            f"{(c['reason'] or '-'):<16} {c['applied_at'][:19]}"
        )

    click.echo()
    conn.close()


@cli.command('batch-train')
@click.option('--days', default=30, help='Number of historical days to train on.')
@click.option('--db-path', default=DEFAULT_DB)
def batch_train_cmd(days, db_path):
    """Replay historical data as corrections to train the system.

    This feeds actual historical covers back as corrections, allowing
    the coefficients to converge toward their true values.
    """
    conn = get_connection(db_path)

    click.echo(f"\n  Training on {days} days of historical data...")
    result = batch_train(conn, days=days)

    click.echo(f"\n  Training complete!")
    click.echo(f"    Days processed:      {result['days_trained']}")
    click.echo(f"    Corrections applied:  {result['corrections_applied']}")
    click.echo(f"    Avg error before:     {result['avg_error_before']:.1f}%")
    click.echo(f"    Avg error after:      {result['avg_error_after']:.1f}%")
    click.echo()

    conn.close()


@cli.command()
@click.option('--coeff-type', default=None, help='Filter by coefficient type.')
@click.option('--db-path', default=DEFAULT_DB)
def convergence(coeff_type, db_path):
    """Show coefficient convergence status.

    Displays how many times each coefficient has been updated and its
    current distance from initial values.
    """
    conn = get_connection(db_path)

    from .config import (
        INIT_DOW_FACTORS, INIT_MONTH_FACTORS, INIT_WEATHER_FACTORS,
        INIT_EVENT_FACTORS, INIT_BASE_DAILY, INIT_HOUR_SHARES,
        TRUE_DOW_FACTORS, TRUE_MONTH_FACTORS, TRUE_WEATHER_FACTORS,
        TRUE_EVENT_FACTORS, TRUE_BASE_DAILY, TRUE_HOUR_SHARES,
    )

    initial_map = {
        'base_daily': {'default': INIT_BASE_DAILY},
        'dow_factor': {str(k): v for k, v in INIT_DOW_FACTORS.items()},
        'month_factor': {str(k): v for k, v in INIT_MONTH_FACTORS.items()},
        'hour_share': {str(k): v for k, v in INIT_HOUR_SHARES.items()},
        'weather_factor': INIT_WEATHER_FACTORS,
        'event_factor': INIT_EVENT_FACTORS,
    }

    true_map = {
        'base_daily': {'default': TRUE_BASE_DAILY},
        'dow_factor': {str(k): v for k, v in TRUE_DOW_FACTORS.items()},
        'month_factor': {str(k): v for k, v in TRUE_MONTH_FACTORS.items()},
        'hour_share': {str(k): v for k, v in TRUE_HOUR_SHARES.items()},
        'weather_factor': TRUE_WEATHER_FACTORS,
        'event_factor': TRUE_EVENT_FACTORS,
    }

    coeffs = load_coefficients(conn)

    click.echo(f"\n  {'='*70}")
    click.echo(f"  Coefficient Convergence Status")
    click.echo(f"  {'='*70}")
    click.echo(f"  {'Type':<16} {'Key':<12} {'Initial':>8} {'Current':>8} {'True':>8} {'Error%':>8} {'Updates':>8}")
    click.echo(f"  {'-'*68}")

    for ct in sorted(coeffs.keys()):
        if coeff_type and ct != coeff_type:
            continue
        for key in sorted(coeffs[ct].keys(), key=lambda k: (k.isdigit(), int(k) if k.isdigit() else 0, k)):
            current = coeffs[ct][key]
            initial = initial_map.get(ct, {}).get(key, current)
            true_val = true_map.get(ct, {}).get(key, current)
            row = get_coefficient(conn, ct, key)
            updates = row['update_count'] if row else 0

            error_pct = abs(current - true_val) / true_val * 100 if true_val != 0 else 0

            click.echo(
                f"  {ct:<16} {key:<12} {initial:>8.4f} {current:>8.4f} {true_val:>8.4f} {error_pct:>7.1f}% {updates:>8}"
            )

    click.echo()
    conn.close()


@cli.command()
@click.argument('target_date')
@click.option('--format', 'fmt', default='csv', type=click.Choice(['csv', 'json']))
@click.option('--output', 'output_path', default=None, help='Output file path.')
@click.option('--weather', default='clear', type=click.Choice(['clear', 'rain', 'snow', 'extreme_heat']))
@click.option('--event', default=None)
@click.option('--db-path', default=DEFAULT_DB)
def export(target_date, fmt, output_path, weather, event, db_path):
    """Export predictions to CSV or JSON."""
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        click.echo("Error: Date must be in YYYY-MM-DD format.", err=True)
        return

    conn = get_connection(db_path)

    cover_pred = predict_covers(conn, d, weather=weather, event=event)
    staff_schedule = predict_staffing(conn, cover_pred)
    ingredient_orders = predict_ingredients(conn, cover_pred)

    if fmt == 'json':
        data = {
            'date': target_date,
            'weather': weather,
            'event': event,
            'covers': {
                'daily_total': cover_pred.daily_total,
                'hourly': {str(h): c for h, c in cover_pred.hourly.items()},
                'trend_factor': cover_pred.trend_factor,
            },
            'staff': {
                'total_labor_cost': staff_schedule.total_labor_cost,
                'assignments': [
                    {'hour': a.hour, 'role': a.role, 'station': a.station,
                     'staff_count': a.staff_count, 'covers': a.covers}
                    for a in staff_schedule.assignments
                ],
            },
            'ingredients': [
                {'name': o.ingredient_name, 'quantity': o.quantity, 'unit': o.unit,
                 'order_date': o.order_date.isoformat(), 'delivery_date': o.delivery_date.isoformat(),
                 'estimated_cost': o.estimated_cost, 'batch_days': o.batch_covers_days}
                for o in ingredient_orders
            ],
        }
        output = json.dumps(data, indent=2)
    else:
        lines = ['section,hour,role,station,staff_count,covers,ingredient,quantity,unit,order_date,delivery_date,cost']
        for h in OPERATING_HOURS:
            lines.append(f"covers,{h:02d}:00,,,,{cover_pred.hourly.get(h,0)},,,,,,")
        for a in staff_schedule.assignments:
            lines.append(f"staff,{a.hour:02d}:00,{a.role},{a.station},{a.staff_count},{a.covers},,,,,,")
        for o in ingredient_orders:
            lines.append(f"ingredients,,,,,,{o.ingredient_name},{o.quantity:.0f},{o.unit},{o.order_date.isoformat()},{o.delivery_date.isoformat()},{o.estimated_cost:.2f}")
        output = '\n'.join(lines)

    if output_path:
        Path(output_path).write_text(output)
        click.echo(f"Exported to {output_path}")
    else:
        click.echo(output)

    conn.close()


def main():
    cli()


if __name__ == '__main__':
    main()
