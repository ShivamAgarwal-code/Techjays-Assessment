"""Configuration constants for the restaurant prediction system."""

# Operating hours (inclusive start, exclusive end for iteration)
OPERATING_HOURS = list(range(11, 23))  # 11:00 AM to 10:00 PM

# --- True factors (used by synthetic data generator) ---
# These are the "ground truth" the feedback loop should converge toward.

TRUE_BASE_DAILY = 150

TRUE_DOW_FACTORS = {
    0: 0.70,  # Monday
    1: 0.75,  # Tuesday
    2: 0.85,  # Wednesday
    3: 0.95,  # Thursday
    4: 1.35,  # Friday
    5: 1.45,  # Saturday
    6: 1.10,  # Sunday
}

TRUE_MONTH_FACTORS = {
    1: 0.80, 2: 0.85, 3: 0.90, 4: 1.00,
    5: 1.05, 6: 1.10, 7: 1.05, 8: 1.00,
    9: 0.95, 10: 1.00, 11: 1.05, 12: 1.20,
}

TRUE_HOUR_SHARES = {
    11: 0.05, 12: 0.14, 13: 0.12, 14: 0.06,
    15: 0.03, 16: 0.03, 17: 0.06, 18: 0.12,
    19: 0.15, 20: 0.12, 21: 0.08, 22: 0.04,
}

TRUE_WEATHER_FACTORS = {
    'clear': 1.00,
    'rain': 0.75,
    'snow': 0.55,
    'extreme_heat': 0.85,
}

TRUE_EVENT_FACTORS = {
    'valentines': 1.45,
    'mothers_day': 1.50,
    'nye': 1.60,
    'superbowl': 1.30,
    'july_4th': 1.25,
    'local_festival': 1.20,
}

# --- Initial (deliberately wrong) coefficients ---
# These are ~10% off from truth so the feedback loop can demonstrate convergence.

INIT_BASE_DAILY = 140  # true: 150

INIT_DOW_FACTORS = {
    0: 0.78,  # true: 0.70
    1: 0.82,  # true: 0.75
    2: 0.90,  # true: 0.85
    3: 1.02,  # true: 0.95
    4: 1.20,  # true: 1.35
    5: 1.30,  # true: 1.45
    6: 1.00,  # true: 1.10
}

INIT_MONTH_FACTORS = {
    1: 0.88, 2: 0.92, 3: 0.95, 4: 1.05,
    5: 1.10, 6: 1.15, 7: 1.00, 8: 0.95,
    9: 1.00, 10: 1.05, 11: 1.10, 12: 1.10,
}

INIT_HOUR_SHARES = {
    11: 0.06, 12: 0.13, 13: 0.11, 14: 0.07,
    15: 0.04, 16: 0.04, 17: 0.07, 18: 0.11,
    19: 0.13, 20: 0.11, 21: 0.09, 22: 0.04,
}

INIT_WEATHER_FACTORS = {
    'clear': 1.00,
    'rain': 0.85,   # true: 0.75
    'snow': 0.65,   # true: 0.55
    'extreme_heat': 0.92,  # true: 0.85
}

INIT_EVENT_FACTORS = {
    'valentines': 1.30,    # true: 1.45
    'mothers_day': 1.35,   # true: 1.50
    'nye': 1.45,           # true: 1.60
    'superbowl': 1.15,     # true: 1.30
    'july_4th': 1.10,      # true: 1.25
    'local_festival': 1.10,  # true: 1.20
}

# Weather probability distribution for synthetic data
WEATHER_DISTRIBUTION = {
    'clear': 0.60,
    'rain': 0.20,
    'snow': 0.10,
    'extreme_heat': 0.10,
}

WEATHER_REASONS = {'clear', 'rain', 'snow', 'extreme_heat'}
EVENT_NAMES = set(TRUE_EVENT_FACTORS.keys())

# --- Staff configuration ---
STAFF_ROLES = [
    {'role': 'chef',       'station': 'kitchen',  'covers_per_staff': 60, 'min_on_shift': 1, 'max_on_shift': 2, 'hourly_rate': 35.00},
    {'role': 'line_cook',  'station': 'grill',    'covers_per_staff': 25, 'min_on_shift': 1, 'max_on_shift': 4, 'hourly_rate': 22.00},
    {'role': 'line_cook',  'station': 'sautee',   'covers_per_staff': 25, 'min_on_shift': 1, 'max_on_shift': 3, 'hourly_rate': 22.00},
    {'role': 'line_cook',  'station': 'prep',     'covers_per_staff': 30, 'min_on_shift': 1, 'max_on_shift': 3, 'hourly_rate': 20.00},
    {'role': 'server',     'station': 'floor',    'covers_per_staff': 15, 'min_on_shift': 2, 'max_on_shift': 8, 'hourly_rate': 12.00},
    {'role': 'host',       'station': 'front',    'covers_per_staff': 80, 'min_on_shift': 1, 'max_on_shift': 2, 'hourly_rate': 14.00},
    {'role': 'bartender',  'station': 'bar',      'covers_per_staff': 30, 'min_on_shift': 1, 'max_on_shift': 3, 'hourly_rate': 18.00},
    {'role': 'dishwasher', 'station': 'dish_pit', 'covers_per_staff': 40, 'min_on_shift': 1, 'max_on_shift': 3, 'hourly_rate': 15.00},
]

MIN_SHIFT_HOURS = 4

# --- Menu / ingredient configuration ---
CATEGORY_RATES = {
    'appetizer': 0.6,
    'main': 1.0,
    'dessert': 0.4,
    'drink': 1.2,
}

WASTE_BUFFER = 0.10  # 10% extra

# --- Feedback loop ---
BASE_ALPHA = 0.15
NOISE_STDDEV_FRACTION = 0.08  # for synthetic data generation
