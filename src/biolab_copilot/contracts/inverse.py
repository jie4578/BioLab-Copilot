"""Versioned contracts for research-only ELISA 4PL inverse estimation."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import ContractBaseModel, ValidationIssue

InverseStatus = Literal[
    "estimated_within_standard_span",
    "below_standard_span",
    "above_standard_span",
    "outside_model_domain",
    "near_asymptote_unstable",
    "numerical_failure",
]
InverseRunStatus = Literal["computed", "partial", "failed"]
DilutionFactorSource = Literal["mapped_field", "uniform_declared"]
SampleSourceMode = Literal["same_import_artifact", "separate_import_artifact"]


def _finite(value: float | None) -> float | None:
    if value is not None and not math.isfinite(value):
        raise ValueError("value must be finite or null")
    return value


class ELISAInverseDesign(ContractBaseModel):
    """Explicit declarations for one research-only inverse run."""

    assay_type: Literal["elisa_standard_curve"] = "elisa_standard_curve"
    intended_use: Literal["research_only"] = "research_only"
    research_only_acknowledged: Literal[True]
    validated_quantification_enabled: Literal[False] = False
    research_estimation_enabled: Literal[True] = True
    curve_context_compatibility_declared: Literal[True]
    curve_context_compatibility_rationale: str = Field(min_length=1)
    sample_source_mode: SampleSourceMode
    sample_artifact_path: str | None = None
    dilution_factor_source: DilutionFactorSource
    dilution_factor_field: Literal["dilution_factor"] | None = None
    uniform_dilution_factor: float | None = Field(default=None, ge=1)
    allow_extrapolation: Literal[False] = False
    response_tolerance: float = Field(default=1e-10, gt=0)
    asymptote_tolerance: float = Field(default=1e-10, gt=0)
    concentration_tolerance: float = Field(default=1e-10, gt=0)
    forward_check_tolerance: float = Field(default=1e-8, gt=0)
    log_overflow_threshold: float = Field(default=700.0, gt=0, lt=709.0)
    warning_confirmations: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_source_and_dilution(self) -> ELISAInverseDesign:
        if self.sample_source_mode == "separate_import_artifact" and not self.sample_artifact_path:
            raise ValueError("sample_artifact_path is required for separate_import_artifact")
        if self.sample_source_mode == "same_import_artifact" and self.sample_artifact_path:
            raise ValueError("sample_artifact_path must be null for same_import_artifact")
        if self.dilution_factor_source == "mapped_field":
            if self.dilution_factor_field != "dilution_factor":
                raise ValueError("mapped_field requires dilution_factor_field=dilution_factor")
            if self.uniform_dilution_factor is not None:
                raise ValueError("uniform_dilution_factor must be null for mapped_field")
        else:
            if self.uniform_dilution_factor is None:
                raise ValueError("uniform_declared requires an explicit uniform_dilution_factor")
            if self.dilution_factor_field is not None:
                raise ValueError("dilution_factor_field must be null for uniform_declared")
        return self


class SampleConcentrationRecord(ContractBaseModel):
    """One sample measurement; no unknown-sample aggregation is represented here."""

    record_number: int = Field(ge=1)
    measurement_id: str = Field(min_length=1)
    sample_id: str | None = None
    replicate_type: str | None = None
    replicate_id: str | None = None
    source_file: str = Field(min_length=1)
    sheet_name: str | None = None
    source_row_number: int | None = Field(default=None, ge=1)
    source_location: str = Field(min_length=1)
    raw_response: str | None = Field(default=None, max_length=200)
    response: float | None = None
    concentration_in_assayed_sample: float | None = None
    dilution_factor: float | None = None
    concentration_in_original_sample: float | None = None
    status: InverseStatus
    reason: str = Field(min_length=1)
    curve_response_lower: float | None = None
    curve_response_upper: float | None = None

    _finite_values = field_validator(
        "response",
        "concentration_in_assayed_sample",
        "dilution_factor",
        "concentration_in_original_sample",
        "curve_response_lower",
        "curve_response_upper",
    )(_finite)


class ExcludedSampleRecord(ContractBaseModel):
    """A retained non-sample row that was not eligible for inverse estimation."""

    record_number: int = Field(ge=1)
    sample_type: str | None = None
    source_location: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SampleConcentrationPreview(ContractBaseModel):
    """Deterministic preview bound into the confirmed inverse plan."""

    preview_id: str = Field(min_length=1)
    curve_fit_result_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    sample_artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    records: list[SampleConcentrationRecord] = Field(default_factory=list)
    excluded_records: list[ExcludedSampleRecord] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    blocking_reasons: list[ValidationIssue] = Field(default_factory=list)
    preview_ready: bool


class SampleConcentrationsResult(ContractBaseModel):
    """Research-only per-measurement inverse output."""

    result_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: InverseRunStatus
    assay_type: Literal["elisa_standard_curve"] = "elisa_standard_curve"
    analysis_level: Literal["measurement_rows"] = "measurement_rows"
    intended_use: Literal["research_only"] = "research_only"
    research_only_acknowledged: Literal[True] = True
    curve_validated: Literal[False] = False
    validated_quantification_enabled: Literal[False] = False
    research_estimation_enabled: Literal[True] = True
    direction: Literal["increasing", "decreasing"]
    concentration_unit: str = Field(min_length=1)
    response_unit: str = Field(min_length=1)
    observed_standard_concentration_span: tuple[float, float] | None = None
    fitted_response_span: tuple[float, float] | None = None
    records: list[SampleConcentrationRecord] = Field(default_factory=list)
    excluded_records: list[ExcludedSampleRecord] = Field(default_factory=list)
    total_sample_measurements: int = Field(ge=0)
    successful_estimates: int = Field(ge=0)
    below_standard_span_count: int = Field(ge=0)
    above_standard_span_count: int = Field(ge=0)
    outside_model_domain_count: int = Field(ge=0)
    near_asymptote_unstable_count: int = Field(ge=0)
    numerical_failure_count: int = Field(ge=0)
    issues: list[ValidationIssue] = Field(default_factory=list)
    source_record_references: dict[str, list[int]] = Field(default_factory=dict)
    curve_fit_result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    sample_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    sample_source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    confirmed_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    inverse_preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    known_limitations: list[str] = Field(default_factory=list)

    @field_validator("observed_standard_concentration_span", "fitted_response_span")
    @classmethod
    def _finite_spans(cls, value: tuple[float, float] | None) -> tuple[float, float] | None:
        if value is not None and not all(math.isfinite(item) for item in value):
            raise ValueError("spans must contain finite values")
        return value


__all__ = [
    "DilutionFactorSource",
    "ELISAInverseDesign",
    "ExcludedSampleRecord",
    "InverseRunStatus",
    "InverseStatus",
    "SampleConcentrationPreview",
    "SampleConcentrationRecord",
    "SampleConcentrationsResult",
    "SampleSourceMode",
]
