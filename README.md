# Restaurant Resource Prediction System

A self-correcting prediction system for restaurant operations that forecasts **customer covers (hourly)**, **staff scheduling (by role/station)**, and **ingredient ordering (with shelf life and lead times)**. The system accepts manager corrections and adjusts its coefficients via exponential smoothing until predictions converge toward accuracy.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database with 2 years of synthetic data
python -m restaurant_predictor init

# Predict for a specific date
python -m restaurant_predictor predict 2025-06-14 --weather clear

# Submit a correction
python -m restaurant_predictor correct 2025-06-14 --predicted 200 --actual 155 --reason rain

# Train on historical data to improve coefficients
python -m restaurant_predictor batch-train --days 60

# See how coefficients are converging
python -m restaurant_predictor convergence

# Run the full demo
bash scripts/demo.sh
```

## Architecture

```
restaurant_predictor/
├── cli.py              # Click CLI (all user-facing commands)
├── db.py               # SQLite schema and query helpers
├── models.py           # Domain dataclasses
├── config.py           # Constants and true/initial coefficient values
├── synthetic.py        # Generates 2 years of realistic synthetic data
├── feedback.py         # Feedback loop with exponential smoothing
├── prediction/
│   ├── covers.py       # Hourly cover prediction engine
│   ├── staffing.py     # Covers → staff schedule by role/station
│   └── ingredients.py  # Covers → ingredient orders with shelf life
data/
└── restaurant.db       # Generated SQLite database
```

## How It Works

### 1. Cover Prediction

The system predicts daily covers using a multiplicative model:

```
predicted_daily = base × dow_factor × month_factor × weather_factor × event_factor × trend
```

Each factor is a coefficient stored in SQLite. Hourly breakdown uses `hour_share` coefficients (fractions that sum to 1.0).

**Factors:**
- **Day-of-week**: Monday (0.70x) through Saturday (1.45x)
- **Monthly seasonality**: January (0.80x) through December (1.20x)
- **Weather**: clear (1.0x), rain (0.75x), snow (0.55x), extreme_heat (0.85x)
- **Events**: Valentine's (1.45x), NYE (1.60x), Mother's Day (1.50x), etc.
- **Trend**: Linear trend from last 90 days, clamped to [0.85, 1.15]

### 2. Staff Scheduling

Converts hourly covers into staff counts by role/station:

| Role | Station | Covers per Staff | Min | Max |
|------|---------|-----------------|-----|-----|
| Chef | kitchen | 60 | 1 | 2 |
| Line Cook | grill | 25 | 1 | 4 |
| Line Cook | sautee | 25 | 1 | 3 |
| Line Cook | prep | 30 | 1 | 3 |
| Server | floor | 15 | 2 | 8 |
| Host | front | 80 | 1 | 2 |
| Bartender | bar | 30 | 1 | 3 |
| Dishwasher | dish_pit | 40 | 1 | 3 |

Staff counts are smoothed with 4-hour minimum shift blocks to avoid calling staff in for single hours.

### 3. Ingredient Ordering

Pipeline:
1. **Menu mix estimation**: Each cover orders ~0.6 appetizers, 1.0 main, 0.4 desserts, 1.2 drinks
2. **Recipe explosion**: Multiply menu item counts by ingredient quantities from recipes
3. **Batch sizing by shelf life**:
   - Perishable (≤3 days): order for 1 day
   - Semi-perishable (4-14 days): order for 3 days
   - Shelf-stable (>14 days): order for 7 days
4. **Adjustments**: 10% waste buffer, subtract current stock, round up to supplier minimums
5. **Lead time**: Order date = needed date - supplier lead time

### 4. Feedback Loop (Key Feature)

When a manager submits a correction ("predicted 120, actual 85, reason: rain"), the system:

1. Computes the error ratio: `85 / 120 = 0.708`
2. Attributes the error to relevant coefficients based on the reason
3. Updates coefficients using **exponential smoothing**:

```
implied_coeff = current × weighted_error_ratio
new_coeff = α × implied + (1-α) × current
```

**Adaptive alpha** (learning rate):
- First 5 corrections: α = 0.30 (learn fast from initial errors)
- Corrections 5-20: α = 0.15 (standard learning)
- After 20: α = 0.075 (fine-tuning)

**Error attribution:**
- Weather reason → update `weather_factor` (100%)
- Event reason → update `event_factor` (100%)
- No reason → split across `dow_factor` (70%) + `base_daily` (30%)

**Convergence**: Coefficients start deliberately ~10% wrong. After batch-training on historical data, they converge toward their true values.

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Create DB and generate 2 years of synthetic data |
| `predict DATE` | Full prediction: covers + staff + ingredients |
| `correct DATE` | Submit manager correction, auto-update coefficients |
| `show-coefficients` | Display all current coefficient values |
| `convergence` | Show coefficient distance from true values |
| `batch-train` | Replay N days of history as corrections (training) |
| `history` | View past predictions and corrections |
| `export DATE` | Export predictions to CSV or JSON |

## Synthetic Dataset

The generated dataset includes:
- **730 days** of hourly cover data (Jan 2024 - Dec 2025) with embedded day-of-week, monthly, weather, and event patterns
- **20 menu items** across 4 categories (appetizers, mains, desserts, drinks)
- **37 ingredients** with realistic shelf lives (chicken: 2 days, flour: 90 days) and lead times
- **Detailed recipes** linking menu items to ingredients with gram quantities
- **8 staff role/station configurations** with covers-per-staff ratios
- **Special events**: Valentine's Day, Mother's Day, NYE, Super Bowl, July 4th, local festivals
- **Gaussian noise** (σ = 8% of expected value) for realism

## Example Output

```
==========================================================
  Prediction for 2025-06-14 (Saturday)
==========================================================
  Weather: clear | Event: none | Trend: 1.020

  --- Hourly Covers ---
  Hour      Covers
  ----------------
  11:00          12
  12:00          33
  ...
  TOTAL         237

  --- Staff Schedule ---
  Hour     chef(kitchen) line_cook(grill) ...  server(floor)
  11:00              1               1    ...            2
  12:00              1               2    ...            3
  ...

  Est. labor cost: $3,124.00

  --- Ingredient Orders ---
  Ingredient             Qty  Unit   Order By     Cost
  Salmon Fillet        3,000  g      2025-06-13   $90.00
  Chicken Breast       4,000  g      2025-06-13   $48.00
  ...
```

## Technology

- **Python 3.8+** (no heavy ML frameworks)
- **SQLite** for persistence
- **NumPy** for synthetic data generation
- **Click** for CLI interface
