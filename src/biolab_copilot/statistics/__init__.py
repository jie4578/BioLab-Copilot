"""Phase 2A deterministic generic-grouped descriptive statistics."""

from .descriptive import STATISTICAL_LIMITATIONS, compute_grouped_descriptive
from .plans import (
    PHASE2A_CONFIRMATION_CODES,
    PHASE2A_STATISTICS,
    ExecutionPreflight,
    build_analysis_plan,
    declared_measurement_units,
    required_confirmation_codes,
    validate_execution_inputs,
)

__all__ = [
    "PHASE2A_CONFIRMATION_CODES",
    "PHASE2A_STATISTICS",
    "STATISTICAL_LIMITATIONS",
    "ExecutionPreflight",
    "build_analysis_plan",
    "compute_grouped_descriptive",
    "declared_measurement_units",
    "required_confirmation_codes",
    "validate_execution_inputs",
]
