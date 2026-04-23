"""Ingredient ordering engine.

Converts cover predictions into ingredient orders, accounting for
menu mix, recipe explosion, shelf life, supplier lead times, and
current stock levels.
"""

import math
from datetime import timedelta
from collections import defaultdict

from ..db import get_all_menu_items, get_all_ingredients, get_recipes_by_menu_item
from ..config import CATEGORY_RATES, WASTE_BUFFER
from ..models import IngredientOrder


def estimate_menu_mix(daily_covers, menu_items):
    """Estimate how many orders of each menu item based on cover count.

    Each cover orders roughly:
    - 0.6 appetizers, 1.0 main, 0.4 desserts, 1.2 drinks
    Distributed within category by popularity_weight.
    """
    orders = {}
    for item in menu_items:
        category_total = daily_covers * CATEGORY_RATES.get(item['category'], 1.0)
        orders[item['id']] = max(1, round(category_total * item['popularity_weight']))
    return orders


def explode_recipes(menu_orders, recipes):
    """Multiply menu item orders by recipe ingredient quantities.

    Returns {ingredient_id: total_quantity_needed}.
    """
    ingredient_needs = defaultdict(float)
    for item_id, order_count in menu_orders.items():
        for recipe_line in recipes.get(item_id, []):
            ingredient_needs[recipe_line['ingredient_id']] += (
                recipe_line['quantity_grams'] * order_count
            )
    return dict(ingredient_needs)


def predict_ingredients(conn, cover_prediction):
    """Generate ingredient orders for a target date.

    Pipeline: covers → menu mix → recipe explosion → batch sizing → orders
    """
    menu_items = get_all_menu_items(conn)
    ingredients = get_all_ingredients(conn)
    recipes = get_recipes_by_menu_item(conn)

    daily_covers = cover_prediction.daily_total
    target_date = cover_prediction.target_date

    # Step 1: Menu mix
    menu_orders = estimate_menu_mix(daily_covers, menu_items)

    # Step 2: Recipe explosion
    ingredient_needs = explode_recipes(menu_orders, recipes)

    # Step 3: Compute orders with shelf life / lead time logic
    orders = []
    for ing_id, daily_need in ingredient_needs.items():
        ing = ingredients.get(ing_id)
        if not ing:
            continue

        # Batch sizing based on shelf life
        shelf_life = ing['shelf_life_days']
        if shelf_life <= 3:
            batch_days = 1  # perishable: order daily
        elif shelf_life <= 14:
            batch_days = min(3, shelf_life - 1)  # semi-perishable
        else:
            batch_days = 7  # shelf-stable: weekly batch

        total_need = daily_need * batch_days

        # Add waste buffer
        total_need *= (1 + WASTE_BUFFER)

        # Subtract current stock
        to_order = max(0, total_need - ing['current_stock'])

        if to_order <= 0:
            continue

        # Round up to min order quantity
        min_qty = ing['min_order_quantity']
        to_order = math.ceil(to_order / min_qty) * min_qty

        # Compute order and delivery dates
        lead_time = ing['supplier_lead_time_days']
        order_date = target_date - timedelta(days=lead_time)
        delivery_date = target_date

        estimated_cost = to_order * ing['cost_per_unit']

        orders.append(IngredientOrder(
            ingredient_id=ing_id,
            ingredient_name=ing['name'],
            quantity=to_order,
            unit=ing['unit'],
            order_date=order_date,
            delivery_date=delivery_date,
            needed_by_date=target_date,
            estimated_cost=estimated_cost,
            batch_covers_days=batch_days,
        ))

    # Sort by order urgency (earliest order_date first)
    orders.sort(key=lambda o: o.order_date)

    return orders
