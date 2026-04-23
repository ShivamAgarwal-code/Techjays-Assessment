"""Data classes for domain objects."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class CoverPrediction:
    target_date: date
    daily_total: int
    hourly: dict  # {hour: count}
    weather: str = 'clear'
    event: Optional[str] = None
    trend_factor: float = 1.0


@dataclass
class StaffAssignment:
    hour: int
    role: str
    station: str
    staff_count: int
    covers: int


@dataclass
class StaffSchedule:
    target_date: date
    assignments: list  # list of StaffAssignment
    total_labor_cost: float = 0.0


@dataclass
class IngredientOrder:
    ingredient_id: int
    ingredient_name: str
    quantity: float
    unit: str
    order_date: date
    delivery_date: date
    needed_by_date: date
    estimated_cost: float
    batch_covers_days: int


@dataclass
class Correction:
    target_date: date
    predicted_value: float
    actual_value: float
    hour: Optional[int] = None
    reason: Optional[str] = None
    coefficients_updated: list = field(default_factory=list)
