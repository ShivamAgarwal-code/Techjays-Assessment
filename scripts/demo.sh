#!/bin/bash
# End-to-end demo of the Restaurant Resource Prediction System
set -e

DB="data/restaurant.db"
CMD="python -m restaurant_predictor"

echo "============================================================"
echo "  Restaurant Resource Prediction System - Demo"
echo "============================================================"
echo

# Step 1: Initialize
echo ">>> Step 1: Initialize database with synthetic data"
$CMD init --db-path $DB --seed 42
echo

# Step 2: Show initial (deliberately wrong) coefficients
echo ">>> Step 2: Show initial coefficients (deliberately inaccurate)"
$CMD show-coefficients --db-path $DB
echo

# Step 3: Show convergence before training
echo ">>> Step 3: Convergence status BEFORE training"
$CMD convergence --db-path $DB
echo

# Step 4: Predict for a Saturday
echo ">>> Step 4: Predict for 2025-06-14 (Saturday, clear weather)"
$CMD predict 2025-06-14 --weather clear --db-path $DB
echo

# Step 5: Submit a correction
echo ">>> Step 5: Submit correction - actual was lower due to rain"
$CMD correct 2025-06-14 --predicted 200 --actual 155 --reason rain --db-path $DB
echo

# Step 6: Batch train on 60 days of historical data
echo ">>> Step 6: Batch train on 60 days of historical data"
$CMD batch-train --days 60 --db-path $DB
echo

# Step 7: Train again for further convergence
echo ">>> Step 7: Second round of batch training (100 days)"
$CMD batch-train --days 100 --db-path $DB
echo

# Step 8: Show convergence after training
echo ">>> Step 8: Convergence status AFTER training"
$CMD convergence --db-path $DB
echo

# Step 9: Predict again - should be more accurate
echo ">>> Step 9: Re-predict for 2025-06-14 with updated coefficients"
$CMD predict 2025-06-14 --weather clear --db-path $DB
echo

# Step 10: Show correction history
echo ">>> Step 10: Recent correction history"
$CMD history --last 10 --db-path $DB
echo

echo "============================================================"
echo "  Demo complete!"
echo "============================================================"
