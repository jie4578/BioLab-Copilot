"""Versioned Pydantic contracts for BioLab Copilot.

This module intentionally contains schemas and validation only. It does not read files,
clean data, calculate statistics, call an LLM, or render reports.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import IssueSeverity, RunStatus

SCHEMA_VERSION = "1.0"
AssayType = Literal["generic_grouped", "elisa_standard_curve"]
AnalysisLevel = Literal["measurement_rows", "experimental_units", "standard_curve_levels"]
DescriptiveStatisticName = Literal["n_measurements", "mean", "median", "min", "max", "sample_sd"]
IndependentTwoGroupDesignType = Literal["independent_two_group"]
TechnicalRepeatPolicy = Literal["none", "mean"]


def _default_descriptive_statistics() -> list[DescriptiveStatisticName]:
    return ["n_measurements", "mean", "median", "min", "max", "sample_sd"]


class ContractBaseModel(BaseModel):
    """Shared serialization and forward-integration configuration."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        pattern=r"^\d+\.\d+$",
        description="Contract schema version, independent of the package version.",
    )
    antibody_id: str | None = Field(default=None, min_length=1)
    sequence_id: str | None = Field(default=None, min_length=1)
    mutation_id: str | None = Field(default=None, min_length=1)
    experiment_id: str | None = Field(default=None, min_length=1)
    sample_id: str | None = Field(default=None, min_length=1)
    experimental_unit_id: str | None = Field(default=None, min_length=1)


class ExperimentSpec(ContractBaseModel):
    """User-confirmable description of one supported experiment."""

    experiment_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    assay_type: AssayType
    description: str | None = None
    source_filename: str = Field(min_length=1)
    configuration: dict[str, Any] = Field(default_factory=dict)


class DatasetProfile(ContractBaseModel):
    """Descriptive facts about an input dataset, without modifying it."""

    dataset_id: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    column_names: list[str] = Field(default_factory=list)
    missing_value_count: int = Field(ge=0)
    duplicate_row_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    analysis_ready: bool = True
    parsed_record_count: int = Field(default=0, ge=0)
    error_record_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    error_count: int = Field(default=0, ge=0)
    blocking_count: int = Field(default=0, ge=0)
    field_profiles: list[FieldProfile] = Field(default_factory=list)
    group_counts: dict[str, int] = Field(default_factory=dict)
    unit_values: dict[str, list[str]] = Field(default_factory=dict)
    duplicate_record_numbers: list[int] = Field(default_factory=list)
    source_sheet_name: str | None = None


class ValidationIssue(ContractBaseModel):
    """A reviewable validation or QC finding."""

    code: str = Field(min_length=1)
    severity: IssueSeverity
    message: str = Field(min_length=1)
    location: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    auto_fixed: bool = False
    source_file: str | None = None
    sheet_name: str | None = None
    record_number: int | None = Field(default=None, ge=1)
    source_row_number: int | None = Field(default=None, ge=1)
    field: str | None = None
    raw_value: str | None = Field(default=None, max_length=200)


class FieldProfile(ContractBaseModel):
    """Observed structural facts for one canonical field."""

    field_name: str = Field(min_length=1)
    source_column: str | None = None
    observed_types: list[str] = Field(default_factory=list)
    non_missing_count: int = Field(default=0, ge=0)
    missing_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    non_finite_count: int = Field(default=0, ge=0)


class IndependentTwoGroupDesign(ContractBaseModel):
    """User-supplied design declaration for the restricted Phase 2B comparison."""

    design_type: IndependentTwoGroupDesignType
    experimental_unit_description: str = Field(min_length=1)
    experimental_unit_id_field: str = Field(min_length=1)
    independence_declared: Literal[True]
    independence_rationale: str = Field(min_length=1)
    group_a: str = Field(min_length=1)
    group_b: str = Field(min_length=1)
    technical_repeat_policy: TechnicalRepeatPolicy
    method: Literal["welch_t"]
    alternative: Literal["two-sided"]
    alpha: float = Field(default=0.05, gt=0, lt=1)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)
    assumptions_acknowledged: Literal[True]

    @model_validator(mode="after")
    def _groups_must_differ(self) -> IndependentTwoGroupDesign:
        if self.group_a == self.group_b:
            raise ValueError("group_a and group_b must be different groups")
        if self.alpha != 0.05:
            raise ValueError("Phase 2B requires alpha=0.05")
        if self.confidence_level != 0.95:
            raise ValueError("Phase 2B requires confidence_level=0.95")
        return self


class AnalysisPlan(ContractBaseModel):
    """An explicit plan awaiting or following user confirmation."""

    plan_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    assay_type: AssayType
    objectives: list[str] = Field(min_length=1)
    requested_outputs: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
    input_artifact_path: str | None = None
    input_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    column_mapping: dict[str, str] = Field(default_factory=dict)
    declared_units: dict[str, str] = Field(default_factory=dict)
    group_field: str = "group"
    measurement_field: str = "measurement"
    analysis_level: AnalysisLevel = "measurement_rows"
    statistics: list[DescriptiveStatisticName] = Field(
        default_factory=_default_descriptive_statistics
    )
    sample_sd_ddof: Literal[1] = 1
    duplicate_record_policy: Literal["retain_and_include_all"] = "retain_and_include_all"
    missing_value_policy: Literal["required_measurements_must_be_present"] = (
        "required_measurements_must_be_present"
    )
    outlier_policy: Literal["preserve_and_do_not_detect"] = "preserve_and_do_not_detect"
    imputation_policy: Literal["forbidden"] = "forbidden"
    transformation_policy: Literal["forbidden"] = "forbidden"
    unit_conversion_policy: Literal["forbidden"] = "forbidden"
    required_confirmations: list[str] = Field(default_factory=list)
    warning_confirmations: dict[str, bool] = Field(default_factory=dict)
    generated_at: datetime | None = None
    design_type: IndependentTwoGroupDesignType | None = None
    experimental_unit_description: str | None = None
    experimental_unit_id_field: str | None = None
    independence_declared: bool | None = None
    independence_rationale: str | None = None
    group_a: str | None = None
    group_b: str | None = None
    technical_repeat_policy: TechnicalRepeatPolicy | None = None
    method: Literal["welch_t"] | None = None
    alternative: Literal["two-sided"] | None = None
    alpha: float | None = Field(default=None, gt=0, lt=1)
    confidence_level: float | None = Field(default=None, gt=0, lt=1)
    assumptions_acknowledged: bool | None = None
    design_declaration_path: str | None = None
    design_declaration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    experimental_unit_preview_path: str | None = None
    preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    curve_direction: Literal["increasing", "decreasing"] | None = None
    curve_context_declared: bool | None = None
    curve_context_description: str | None = None
    standard_replicate_policy: Literal["none", "mean_by_concentration"] | None = None
    standard_repeat_id_field: Literal["replicate_id", "technical_replicate_id"] | None = None
    blank_policy: Literal["none"] | None = None
    weighting: Literal["none"] | None = None
    loss: Literal["linear"] | None = None
    optimizer: Literal["scipy.optimize.least_squares"] | None = None
    optimizer_settings: dict[str, float | int] = Field(default_factory=dict)
    parameter_bounds: dict[str, tuple[float, float]] = Field(default_factory=dict)
    initial_starts: list[dict[str, float]] = Field(default_factory=list)
    diagnostic_thresholds: dict[str, float] = Field(default_factory=dict)
    standards_preview_path: str | None = None
    standards_preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    curve_design_path: str | None = None
    curve_design_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    included_standard_record_numbers: list[int] = Field(default_factory=list)
    excluded_record_reasons: dict[str, str] = Field(default_factory=dict)


class StatisticRecord(ContractBaseModel):
    """A structured statistic produced by deterministic software in a later phase."""

    name: str = Field(min_length=1)
    value: float | int | None = None
    unit: str | None = None
    group: str | None = None
    method: str | None = None


class GroupDescriptiveStats(ContractBaseModel):
    """Deterministic descriptive statistics for one measurement-level group."""

    group: str = Field(min_length=1)
    n_measurements: int = Field(ge=1)
    mean: float
    median: float
    min: float
    max: float
    sample_sd: float | None = Field(default=None, ge=0)
    sample_sd_reason: str | None = None
    source_record_numbers: list[int] = Field(min_length=1)

    @field_validator("mean", "median", "min", "max", "sample_sd")
    @classmethod
    def _require_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("descriptive statistics must be finite or null")
        return value


class ExperimentalUnitPreviewRow(ContractBaseModel):
    """One source record as shown in the Phase 2B experimental-unit preview."""

    record_number: int = Field(ge=1)
    experimental_unit_id: str | None = None
    group: str | None = None
    measurement: float | None = None
    technical_repeat_id: str | None = None
    source_location: str = Field(min_length=1)
    issue_codes: list[str] = Field(default_factory=list)

    @field_validator("measurement")
    @classmethod
    def _preview_measurement_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("preview measurements must be finite or null")
        return value


class ExperimentalUnitRecord(ContractBaseModel):
    """One experimental unit after the explicitly declared repeat policy."""

    experimental_unit_id: str = Field(min_length=1)
    group: str = Field(min_length=1)
    n_measurements: int = Field(ge=1)
    technical_repeat_count: int = Field(ge=1)
    technical_repeat_ids: list[str] = Field(default_factory=list)
    measurement_values: list[float] = Field(min_length=1)
    aggregated_value: float
    source_record_numbers: list[int] = Field(min_length=1)
    source_locations: list[str] = Field(min_length=1)

    @field_validator("measurement_values")
    @classmethod
    def _measurement_values_finite(cls, values: list[float]) -> list[float]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("experimental-unit measurements must be finite")
        return values

    @field_validator("aggregated_value")
    @classmethod
    def _aggregated_value_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("aggregated values must be finite")
        return value


class ExperimentalGroupPreview(ContractBaseModel):
    """Counts and repeat structure for one planned comparison group."""

    group: str = Field(min_length=1)
    n_measurements: int = Field(ge=0)
    n_experimental_units: int = Field(ge=0)
    technical_repeat_counts: dict[str, int] = Field(default_factory=dict)


class ExperimentalUnitsPreview(ContractBaseModel):
    """Reproducible preview of experimental-unit assignment and aggregation."""

    preview_id: str = Field(min_length=1)
    input_artifact_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    design_type: IndependentTwoGroupDesignType
    group_a: str = Field(min_length=1)
    group_b: str = Field(min_length=1)
    technical_repeat_policy: TechnicalRepeatPolicy
    rows: list[ExperimentalUnitPreviewRow] = Field(default_factory=list)
    units: list[ExperimentalUnitRecord] = Field(default_factory=list)
    groups: list[ExperimentalGroupPreview] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    blocking_reasons: list[ValidationIssue] = Field(default_factory=list)
    preview_ready: bool


class InferentialGroupStats(ContractBaseModel):
    """Summary of one group at experimental-unit level."""

    group: str = Field(min_length=1)
    n_measurements: int = Field(ge=1)
    n_experimental_units: int = Field(ge=1)
    mean: float
    sample_sd: float
    technical_repeat_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("mean", "sample_sd")
    @classmethod
    def _group_stat_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("inferential group statistics must be finite")
        return value


class AnalysisResult(ContractBaseModel):
    """Structured analysis output; no narrative or LLM-generated values."""

    result_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: Literal["computed", "partial", "failed"]
    statistics: list[StatisticRecord] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    analysis_level: AnalysisLevel = "measurement_rows"
    group_statistics: list[GroupDescriptiveStats] = Field(default_factory=list)
    declared_units: dict[str, str] = Field(default_factory=dict)
    source_record_references: dict[str, list[int]] = Field(default_factory=dict)
    independent_biological_n: int | None = None
    input_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    confirmed_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    statistical_limitations: list[str] = Field(default_factory=list)
    independence_status: Literal["user_declared_not_verified"] | None = None
    group_a: str | None = None
    group_b: str | None = None
    method: Literal["welch_t"] | None = None
    alternative: Literal["two-sided"] | None = None
    alpha: float | None = Field(default=None, gt=0, lt=1)
    confidence_level: float | None = Field(default=None, gt=0, lt=1)
    technical_repeat_policy: TechnicalRepeatPolicy | None = None
    experimental_unit_summaries: list[ExperimentalUnitRecord] = Field(default_factory=list)
    inferential_group_statistics: list[InferentialGroupStats] = Field(default_factory=list)
    mean_difference: float | None = None
    mean_difference_ci_lower: float | None = None
    mean_difference_ci_upper: float | None = None
    t_statistic: float | None = None
    degrees_of_freedom: float | None = None
    p_value: float | None = None
    preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    known_limitations: list[str] = Field(default_factory=list)

    @field_validator(
        "mean_difference",
        "mean_difference_ci_lower",
        "mean_difference_ci_upper",
        "t_statistic",
        "degrees_of_freedom",
        "p_value",
        "alpha",
        "confidence_level",
    )
    @classmethod
    def _result_values_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("analysis result values must be finite or null")
        return value


class ChartArtifact(ContractBaseModel):
    """Metadata for a chart generated from a structured analysis result."""

    artifact_id: str = Field(min_length=1)
    result_id: str = Field(min_length=1)
    chart_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    path: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    source_data_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class ReportArtifact(ContractBaseModel):
    """Metadata for a reproducible report artifact."""

    artifact_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    report_type: Literal["docx", "xlsx", "json"]
    path: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class InputFile(ContractBaseModel):
    """Immutable input-file identity recorded by a run manifest."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    size_bytes: int = Field(ge=0)


class ArtifactFile(ContractBaseModel):
    """A generated file recorded by a run manifest."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    size_bytes: int = Field(ge=0)
    artifact_type: str = Field(min_length=1)


class ImportedRecord(ContractBaseModel):
    """One preserved source record with raw and parsed views."""

    record_number: int = Field(ge=1)
    source_file: str = Field(min_length=1)
    sheet_name: str | None = None
    source_row_number: int | None = Field(default=None, ge=1)
    raw_values: dict[str, Any] = Field(default_factory=dict)
    parsed_values: dict[str, Any] = Field(default_factory=dict)
    source_locations: dict[str, str] = Field(default_factory=dict)


class ImportResult(ContractBaseModel):
    """Traceable output of Phase 1 import and structural QC."""

    input_file: InputFile
    experiment_type: AssayType
    column_mapping: dict[str, str] = Field(default_factory=dict)
    parse_configuration: dict[str, Any] = Field(default_factory=dict)
    dataset_profile: DatasetProfile
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    records: list[ImportedRecord] = Field(default_factory=list)
    analysis_ready: bool


class RunManifest(ContractBaseModel):
    """Audit envelope for one future analysis run."""

    run_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    status: RunStatus
    input_files: list[InputFile] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    software_versions: dict[str, str] = Field(default_factory=dict)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    assay_type: AssayType | None = None
    column_mapping: dict[str, str] = Field(default_factory=dict)
    parse_configuration: dict[str, Any] = Field(default_factory=dict)
    output_files: list[ArtifactFile] = Field(default_factory=list)
    analysis_ready: bool = False
    analysis_level: AnalysisLevel | None = None
    input_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    analysis_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    method: Literal["welch_t", "four_parameter_logistic"] | None = None
    independence_status: Literal["user_declared_not_verified"] | None = None
    curve_validated: Literal[False] | None = None
    quantification_enabled: Literal[False] | None = None
    standards_preview_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


__all__ = [
    "SCHEMA_VERSION",
    "ArtifactFile",
    "AnalysisPlan",
    "AnalysisResult",
    "AnalysisLevel",
    "AssayType",
    "ChartArtifact",
    "ContractBaseModel",
    "DatasetProfile",
    "ExperimentalGroupPreview",
    "ExperimentalUnitPreviewRow",
    "ExperimentalUnitRecord",
    "ExperimentalUnitsPreview",
    "IndependentTwoGroupDesign",
    "InferentialGroupStats",
    "ExperimentSpec",
    "InputFile",
    "ImportResult",
    "ImportedRecord",
    "FieldProfile",
    "ReportArtifact",
    "RunManifest",
    "StatisticRecord",
    "DescriptiveStatisticName",
    "GroupDescriptiveStats",
    "IndependentTwoGroupDesignType",
    "TechnicalRepeatPolicy",
    "ValidationIssue",
]
