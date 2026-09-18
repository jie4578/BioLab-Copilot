"""Versioned contracts for the restricted Phase 3A ELISA workflow."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import ContractBaseModel, ValidationIssue

CurveDirection = Literal["increasing", "decreasing"]
StandardReplicatePolicy = Literal["none", "mean_by_concentration"]
CurveFitStatus = Literal["computed", "failed"]


def _finite(value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError("value must be finite or null")
    return value


class ELISA4PLDesign(ContractBaseModel):
    """User declaration for one standard curve context and one fixed 4PL direction."""

    assay_type: Literal["elisa_standard_curve"] = "elisa_standard_curve"
    curve_context_declared: Literal[True]
    curve_context_description: str = Field(min_length=1)
    concentration_unit: str = Field(min_length=1)
    response_unit: str = Field(min_length=1)
    direction: CurveDirection
    standard_replicate_policy: StandardReplicatePolicy
    standard_repeat_id_field: Literal["replicate_id", "technical_replicate_id"] | None = None
    blank_policy: Literal["none"] = "none"
    weighting: Literal["none"] = "none"
    loss: Literal["linear"] = "linear"
    optimizer: Literal["scipy.optimize.least_squares"] = "scipy.optimize.least_squares"
    ftol: float = Field(default=1e-12, gt=0, lt=1)
    xtol: float = Field(default=1e-12, gt=0, lt=1)
    gtol: float = Field(default=1e-12, gt=0, lt=1)
    max_nfev: int = Field(default=2000, ge=1, le=100_000)
    max_starts: int = Field(default=12, ge=1, le=100)
    boundary_proximity_threshold: float = Field(default=1e-6, gt=0, lt=0.5)
    jacobian_condition_threshold: float = Field(default=1e10, gt=1)

    @model_validator(mode="after")
    def _repeat_identifier_is_explicit(self) -> ELISA4PLDesign:
        if self.standard_replicate_policy == "mean_by_concentration":
            if self.standard_repeat_id_field is None:
                raise ValueError("standard_repeat_id_field is required for mean_by_concentration")
        elif self.standard_repeat_id_field is not None:
            raise ValueError("standard_repeat_id_field must be null when policy is none")
        return self


class CurveParameterBounds(ContractBaseModel):
    """Numerical bounds used by the deterministic optimizer, not biological claims."""

    lower_asymptote: tuple[float, float]
    upper_asymptote: tuple[float, float]
    midpoint_concentration: tuple[float, float]
    slope_magnitude: tuple[float, float]

    @field_validator(
        "lower_asymptote", "upper_asymptote", "midpoint_concentration", "slope_magnitude"
    )
    @classmethod
    def _valid_bounds(cls, value: tuple[float, float]) -> tuple[float, float]:
        if (
            len(value) != 2
            or not all(math.isfinite(item) for item in value)
            or value[0] >= value[1]
        ):
            raise ValueError("parameter bounds must be two finite increasing values")
        return value


class StandardRecordPreview(ContractBaseModel):
    """One preserved input record and its explicit inclusion decision."""

    record_number: int = Field(ge=1)
    source_location: str = Field(min_length=1)
    sample_id: str | None = None
    sample_type: str | None = None
    raw_concentration: str | None = Field(default=None, max_length=200)
    parsed_concentration: float | None = None
    raw_response: str | None = Field(default=None, max_length=200)
    parsed_response: float | None = None
    repeat_id: str | None = None
    included: bool
    exclusion_reason: str | None = None

    _finite_fields = field_validator("parsed_concentration", "parsed_response")(_finite)


class StandardLevelPreview(ContractBaseModel):
    """One concentration level used as one equally weighted fit observation."""

    concentration: float = Field(ge=0)
    n_measurements: int = Field(ge=1)
    response_mean: float
    response_sd: float | None = Field(default=None, ge=0)
    source_record_numbers: list[int] = Field(min_length=1)
    source_locations: list[str] = Field(min_length=1)
    repeat_ids: list[str] = Field(default_factory=list)

    _finite_fields = field_validator("concentration", "response_mean", "response_sd")(_finite)


class StandardsPreview(ContractBaseModel):
    """Deterministic standard inclusion and concentration-level aggregation preview."""

    preview_id: str = Field(min_length=1)
    input_artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    assay_type: Literal["elisa_standard_curve"] = "elisa_standard_curve"
    curve_context_description: str = Field(min_length=1)
    concentration_unit: str = Field(min_length=1)
    response_unit: str = Field(min_length=1)
    direction: CurveDirection
    standard_replicate_policy: StandardReplicatePolicy
    records: list[StandardRecordPreview] = Field(default_factory=list)
    fit_levels: list[StandardLevelPreview] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    blocking_reasons: list[ValidationIssue] = Field(default_factory=list)
    preview_ready: bool


class CurveStartDiagnostic(ContractBaseModel):
    """Outcome of one deterministic 4PL optimizer start."""

    start_index: int = Field(ge=0)
    initial_parameters: dict[str, float]
    success: bool
    objective_sse: float | None = Field(default=None, ge=0)
    nfev: int | None = Field(default=None, ge=0)
    termination_status: int | None = None
    termination_reason: str | None = None
    failure_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)

    _finite_sse = field_validator("objective_sse")(_finite)


class CurveFitPoint(ContractBaseModel):
    """Observed and predicted response at one fitted concentration level."""

    concentration: float = Field(ge=0)
    observed: float
    predicted: float
    residual: float
    n_measurements: int = Field(ge=1)
    source_record_numbers: list[int] = Field(min_length=1)

    _finite_fields = field_validator("concentration", "observed", "predicted", "residual")(_finite)


class CurveFitResult(ContractBaseModel):
    """Traceable 4PL standard-only result; never a concentration back-calculation result."""

    result_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: CurveFitStatus
    assay_type: Literal["elisa_standard_curve"] = "elisa_standard_curve"
    analysis_level: Literal["standard_curve_levels"] = "standard_curve_levels"
    direction: CurveDirection
    concentration_unit: str = Field(min_length=1)
    response_unit: str = Field(min_length=1)
    lower_asymptote: float | None = None
    upper_asymptote: float | None = None
    midpoint_concentration: float | None = None
    slope_magnitude: float | None = None
    parameter_semantics: dict[str, str] = Field(default_factory=dict)
    fit_points: list[CurveFitPoint] = Field(default_factory=list)
    n_fit_levels: int = Field(default=0, ge=0)
    n_raw_standard_measurements: int = Field(default=0, ge=0)
    observed_standard_concentration_span: tuple[float, float] | None = None
    midpoint_within_observed_positive_span: bool | None = None
    sse: float | None = Field(default=None, ge=0)
    rmse: float | None = Field(default=None, ge=0)
    r_squared: float | None = None
    r_squared_reason: str | None = None
    convergence_status: str | None = None
    termination_reason: str | None = None
    selected_start_index: int | None = Field(default=None, ge=0)
    start_diagnostics: list[CurveStartDiagnostic] = Field(default_factory=list)
    parameter_boundary_flags: dict[str, bool] = Field(default_factory=dict)
    jacobian_rank: int | None = Field(default=None, ge=0)
    jacobian_condition_number: float | None = None
    jacobian_scale_description: str | None = None
    curve_validated: Literal[False] = False
    quantification_enabled: Literal[False] = False
    issues: list[ValidationIssue] = Field(default_factory=list)
    source_record_references: dict[str, list[int]] = Field(default_factory=dict)
    input_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    confirmed_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    standards_preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    known_limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "lower_asymptote",
        "upper_asymptote",
        "midpoint_concentration",
        "slope_magnitude",
        "sse",
        "rmse",
        "r_squared",
        "jacobian_condition_number",
    )
    @classmethod
    def _result_finite(cls, value: float | None) -> float | None:
        return _finite(value)

    @model_validator(mode="after")
    def _parameter_constraints(self) -> CurveFitResult:
        if self.status == "computed":
            lower = self.lower_asymptote
            upper = self.upper_asymptote
            midpoint = self.midpoint_concentration
            slope = self.slope_magnitude
            if any(value is None for value in (lower, upper, midpoint, slope)):
                raise ValueError("computed results require all four 4PL parameters")
            assert lower is not None
            assert upper is not None
            assert midpoint is not None
            assert slope is not None
            if not (upper > lower and midpoint > 0 and slope > 0):
                raise ValueError("computed 4PL parameters violate their constraints")
        return self


__all__ = [
    "CurveDirection",
    "CurveFitPoint",
    "CurveFitResult",
    "CurveFitStatus",
    "CurveParameterBounds",
    "CurveStartDiagnostic",
    "ELISA4PLDesign",
    "StandardLevelPreview",
    "StandardRecordPreview",
    "StandardReplicatePolicy",
    "StandardsPreview",
]
