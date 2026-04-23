"""Synthetic data generator for the restaurant prediction system.

Generates 2 years of historical cover data with embedded patterns for
day-of-week, monthly seasonality, weather effects, and special events.
Also seeds menu items, ingredients, recipes, and staff roles.
"""

import numpy as np
from datetime import date, timedelta, datetime

from .config import (
    TRUE_BASE_DAILY, TRUE_DOW_FACTORS, TRUE_MONTH_FACTORS,
    TRUE_HOUR_SHARES, TRUE_WEATHER_FACTORS, TRUE_EVENT_FACTORS,
    INIT_BASE_DAILY, INIT_DOW_FACTORS, INIT_MONTH_FACTORS,
    INIT_HOUR_SHARES, INIT_WEATHER_FACTORS, INIT_EVENT_FACTORS,
    WEATHER_DISTRIBUTION, OPERATING_HOURS, STAFF_ROLES,
    NOISE_STDDEV_FRACTION,
)
from .db import init_db, save_coefficient


def generate_synthetic_data(conn, seed=42, num_days=730):
    """Generate all synthetic data and initialize the database."""
    rng = np.random.default_rng(seed)

    init_db(conn)
    _seed_staff_roles(conn)
    _seed_menu_and_ingredients(conn)
    _seed_historical_covers(conn, rng, num_days)
    _seed_initial_coefficients(conn)

    conn.commit()


def _seed_staff_roles(conn):
    for role in STAFF_ROLES:
        conn.execute("""
            INSERT OR IGNORE INTO staff_roles (role, station, covers_per_staff, min_on_shift, max_on_shift, hourly_rate)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (role['role'], role['station'], role['covers_per_staff'],
              role['min_on_shift'], role['max_on_shift'], role['hourly_rate']))


def _seed_menu_and_ingredients(conn):
    # Menu items: name, category, popularity_weight
    menu_items = [
        # Appetizers (weights sum to ~1.0 within category)
        ('Caesar Salad', 'appetizer', 0.25),
        ('Bruschetta', 'appetizer', 0.20),
        ('Soup of the Day', 'appetizer', 0.20),
        ('Calamari', 'appetizer', 0.20),
        ('Shrimp Cocktail', 'appetizer', 0.15),
        # Mains
        ('Grilled Salmon', 'main', 0.18),
        ('Ribeye Steak', 'main', 0.16),
        ('Chicken Parmesan', 'main', 0.15),
        ('Pasta Carbonara', 'main', 0.14),
        ('Fish and Chips', 'main', 0.12),
        ('Vegetable Risotto', 'main', 0.13),
        ('Lamb Chops', 'main', 0.12),
        # Desserts
        ('Tiramisu', 'dessert', 0.30),
        ('Chocolate Cake', 'dessert', 0.30),
        ('Creme Brulee', 'dessert', 0.25),
        ('Fruit Tart', 'dessert', 0.15),
        # Drinks
        ('House Wine', 'drink', 0.30),
        ('Craft Beer', 'drink', 0.25),
        ('Cocktail', 'drink', 0.25),
        ('Espresso', 'drink', 0.20),
    ]

    for name, category, weight in menu_items:
        conn.execute("""
            INSERT OR IGNORE INTO menu_items (name, category, popularity_weight)
            VALUES (?, ?, ?)
        """, (name, category, weight))

    # Ingredients: name, unit, shelf_life_days, supplier_lead_time_days, min_order_qty, cost_per_unit
    ingredients = [
        # Proteins
        ('Chicken Breast', 'g', 2, 1, 1000, 0.012),
        ('Salmon Fillet', 'g', 2, 1, 1000, 0.030),
        ('Ribeye Beef', 'g', 3, 1, 2000, 0.035),
        ('Shrimp', 'g', 2, 1, 500, 0.028),
        ('Lamb Rack', 'g', 3, 1, 1000, 0.040),
        ('Calamari', 'g', 2, 1, 500, 0.022),
        ('White Fish', 'g', 2, 1, 1000, 0.018),
        # Vegetables
        ('Lettuce', 'g', 3, 1, 500, 0.004),
        ('Tomato', 'g', 4, 1, 1000, 0.005),
        ('Onion', 'g', 14, 1, 2000, 0.003),
        ('Potato', 'g', 14, 1, 5000, 0.002),
        ('Broccoli', 'g', 4, 1, 500, 0.006),
        ('Asparagus', 'g', 3, 1, 500, 0.012),
        ('Mushroom', 'g', 4, 1, 500, 0.010),
        ('Lemon', 'g', 7, 1, 500, 0.006),
        ('Garlic', 'g', 30, 3, 500, 0.008),
        # Dairy
        ('Butter', 'g', 14, 1, 1000, 0.008),
        ('Heavy Cream', 'ml', 7, 1, 1000, 0.006),
        ('Parmesan Cheese', 'g', 30, 3, 500, 0.025),
        ('Mozzarella', 'g', 7, 1, 500, 0.015),
        ('Eggs', 'units', 14, 1, 30, 0.25),
        # Pantry
        ('Flour', 'g', 90, 3, 5000, 0.001),
        ('Rice', 'g', 90, 3, 5000, 0.002),
        ('Pasta', 'g', 90, 3, 5000, 0.003),
        ('Olive Oil', 'ml', 180, 3, 2000, 0.008),
        ('Bread', 'g', 2, 1, 1000, 0.005),
        ('Panko Breadcrumbs', 'g', 60, 3, 1000, 0.004),
        ('Arborio Rice', 'g', 90, 3, 2000, 0.005),
        ('Tomato Sauce', 'g', 30, 3, 2000, 0.004),
        # Beverages
        ('House Red Wine', 'ml', 365, 5, 6000, 0.008),
        ('House White Wine', 'ml', 365, 5, 6000, 0.008),
        ('Craft Beer', 'ml', 90, 5, 12000, 0.004),
        ('Spirits', 'ml', 365, 5, 3000, 0.020),
        ('Coffee Beans', 'g', 30, 3, 1000, 0.025),
        # Garnishes / misc
        ('Fresh Herbs', 'g', 3, 1, 200, 0.020),
        ('Sugar', 'g', 180, 3, 2000, 0.002),
        ('Chocolate', 'g', 60, 3, 500, 0.018),
    ]

    for name, unit, shelf, lead, min_qty, cost in ingredients:
        conn.execute("""
            INSERT OR IGNORE INTO ingredients (name, unit, shelf_life_days, supplier_lead_time_days, min_order_quantity, cost_per_unit, current_stock)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (name, unit, shelf, lead, min_qty, cost))

    conn.commit()

    # Build recipes: map menu items to ingredients
    # Fetch IDs
    item_ids = {r[0]: r[1] for r in conn.execute("SELECT name, id FROM menu_items").fetchall()}
    ing_ids = {r[0]: r[1] for r in conn.execute("SELECT name, id FROM ingredients").fetchall()}

    recipes = {
        'Caesar Salad': [('Lettuce', 120), ('Parmesan Cheese', 30), ('Bread', 40), ('Olive Oil', 15), ('Eggs', 1), ('Garlic', 5), ('Lemon', 10)],
        'Bruschetta': [('Bread', 80), ('Tomato', 60), ('Olive Oil', 15), ('Garlic', 5), ('Fresh Herbs', 5)],
        'Soup of the Day': [('Onion', 50), ('Potato', 80), ('Butter', 20), ('Heavy Cream', 50), ('Garlic', 5), ('Fresh Herbs', 3)],
        'Calamari': [('Calamari', 150), ('Flour', 30), ('Olive Oil', 40), ('Lemon', 15), ('Tomato Sauce', 30)],
        'Shrimp Cocktail': [('Shrimp', 120), ('Lemon', 15), ('Tomato Sauce', 30), ('Lettuce', 30), ('Fresh Herbs', 3)],
        'Grilled Salmon': [('Salmon Fillet', 200), ('Butter', 30), ('Lemon', 20), ('Asparagus', 100), ('Rice', 150), ('Fresh Herbs', 5)],
        'Ribeye Steak': [('Ribeye Beef', 300), ('Butter', 40), ('Potato', 200), ('Asparagus', 80), ('Garlic', 10), ('Fresh Herbs', 5)],
        'Chicken Parmesan': [('Chicken Breast', 200), ('Mozzarella', 60), ('Tomato Sauce', 80), ('Panko Breadcrumbs', 30), ('Pasta', 150), ('Parmesan Cheese', 20)],
        'Pasta Carbonara': [('Pasta', 180), ('Eggs', 2), ('Parmesan Cheese', 40), ('Heavy Cream', 50), ('Garlic', 5), ('Onion', 30)],
        'Fish and Chips': [('White Fish', 200), ('Potato', 250), ('Flour', 40), ('Olive Oil', 60), ('Lemon', 10)],
        'Vegetable Risotto': [('Arborio Rice', 180), ('Mushroom', 60), ('Broccoli', 60), ('Onion', 40), ('Parmesan Cheese', 30), ('Butter', 25), ('Garlic', 5)],
        'Lamb Chops': [('Lamb Rack', 250), ('Potato', 180), ('Garlic', 10), ('Fresh Herbs', 8), ('Butter', 30), ('Olive Oil', 15)],
        'Tiramisu': [('Eggs', 2), ('Sugar', 40), ('Coffee Beans', 10), ('Heavy Cream', 60), ('Chocolate', 20)],
        'Chocolate Cake': [('Flour', 60), ('Sugar', 50), ('Chocolate', 80), ('Butter', 40), ('Eggs', 2), ('Heavy Cream', 30)],
        'Creme Brulee': [('Eggs', 3), ('Heavy Cream', 100), ('Sugar', 40)],
        'Fruit Tart': [('Flour', 50), ('Butter', 30), ('Sugar', 30), ('Eggs', 1), ('Heavy Cream', 30), ('Lemon', 20)],
        'House Wine': [('House Red Wine', 100), ('House White Wine', 100)],
        'Craft Beer': [('Craft Beer', 330)],
        'Cocktail': [('Spirits', 60), ('Lemon', 15), ('Sugar', 10)],
        'Espresso': [('Coffee Beans', 18)],
    }

    for item_name, recipe_lines in recipes.items():
        item_id = item_ids.get(item_name)
        if not item_id:
            continue
        for ing_name, qty in recipe_lines:
            ing_id = ing_ids.get(ing_name)
            if not ing_id:
                continue
            conn.execute("""
                INSERT OR IGNORE INTO recipes (menu_item_id, ingredient_id, quantity_grams)
                VALUES (?, ?, ?)
            """, (item_id, ing_id, qty))

    conn.commit()


def _get_event_for_date(d):
    """Return event name if date is a special event, else None."""
    md = (d.month, d.day)

    if md == (2, 14):
        return 'valentines'
    if md == (12, 31):
        return 'nye'
    if md == (7, 4):
        return 'july_4th'

    # Mother's Day: 2nd Sunday of May
    if d.month == 5 and d.weekday() == 6:
        first_day = date(d.year, 5, 1)
        first_sunday = first_day + timedelta(days=(6 - first_day.weekday()) % 7)
        second_sunday = first_sunday + timedelta(days=7)
        if d == second_sunday:
            return 'mothers_day'

    # Super Bowl: 1st Sunday of February
    if d.month == 2 and d.weekday() == 6:
        first_day = date(d.year, 2, 1)
        first_sunday = first_day + timedelta(days=(6 - first_day.weekday()) % 7)
        if d == first_sunday:
            return 'superbowl'

    return None


def _seed_historical_covers(conn, rng, num_days):
    """Generate historical covers with embedded patterns."""
    start_date = date(2024, 1, 1)
    weather_types = list(WEATHER_DISTRIBUTION.keys())
    weather_probs = list(WEATHER_DISTRIBUTION.values())

    # Pre-assign ~6 local festivals per year
    all_dates = [start_date + timedelta(days=i) for i in range(num_days)]
    festival_dates = set()
    for year in range(start_date.year, start_date.year + 3):
        year_dates = [d for d in all_dates if d.year == year]
        if year_dates:
            indices = rng.choice(len(year_dates), size=min(6, len(year_dates)), replace=False)
            for idx in indices:
                festival_dates.add(year_dates[idx])

    for i in range(num_days):
        d = start_date + timedelta(days=i)
        dow = d.weekday()
        month = d.month

        # Base calculation
        base = TRUE_BASE_DAILY
        base *= TRUE_DOW_FACTORS[dow]
        base *= TRUE_MONTH_FACTORS[month]

        # Weather
        weather = rng.choice(weather_types, p=weather_probs)
        base *= TRUE_WEATHER_FACTORS[weather]

        # Events
        event = _get_event_for_date(d)
        if event is None and d in festival_dates:
            event = 'local_festival'
        if event:
            base *= TRUE_EVENT_FACTORS.get(event, 1.0)

        daily_total = base
        is_holiday = 1 if event in ('july_4th', 'nye') else 0

        # Generate hourly breakdown
        for hour in OPERATING_HOURS:
            share = TRUE_HOUR_SHARES[hour]
            hourly_covers = daily_total * share
            # Add noise
            noise = rng.normal(0, NOISE_STDDEV_FRACTION * hourly_covers)
            hourly_covers = max(0, round(hourly_covers + noise))

            conn.execute("""
                INSERT OR IGNORE INTO historical_covers
                (date, hour, covers, day_of_week, month, is_holiday, event_name, weather)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (d.isoformat(), hour, hourly_covers, dow, month, is_holiday, event, weather))

    conn.commit()


def _seed_initial_coefficients(conn):
    """Seed coefficients with deliberately inaccurate initial values."""
    now = datetime.now().isoformat()

    # Base daily
    save_coefficient(conn, 'base_daily', 'default', INIT_BASE_DAILY, 0)

    # Day of week factors
    for dow, val in INIT_DOW_FACTORS.items():
        save_coefficient(conn, 'dow_factor', str(dow), val, 0)

    # Month factors
    for month, val in INIT_MONTH_FACTORS.items():
        save_coefficient(conn, 'month_factor', str(month), val, 0)

    # Hour shares
    for hour, val in INIT_HOUR_SHARES.items():
        save_coefficient(conn, 'hour_share', str(hour), val, 0)

    # Weather factors
    for weather, val in INIT_WEATHER_FACTORS.items():
        save_coefficient(conn, 'weather_factor', weather, val, 0)

    # Event factors
    for event, val in INIT_EVENT_FACTORS.items():
        save_coefficient(conn, 'event_factor', event, val, 0)
