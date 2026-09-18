"""Deterministic generic-grouped statistics for Phases 2A and 2B."""

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
from .welch import (
    WELCH_LIMITATIONS,
    WelchExecutionPreflight,
    WelchPlanBuild,
    build_welch_plan,
    compute_welch_result,
    validate_welch_execution_inputs,
    welch_software_versions,
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
    "WELCH_LIMITATIONS",
    "WelchExecutionPreflight",
    "WelchPlanBuild",
    "build_welch_plan",
    "compute_welch_result",
    "validate_welch_execution_inputs",
    "welch_software_versions",
]
