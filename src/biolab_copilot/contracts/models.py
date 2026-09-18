"""Versioned Pydantic contracts for BioLab Copilot.

This module intentionally contains schemas and validation only. It does not read files,
clean data, calculate statistics, call an LLM, or render reports.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import IssueSeverity, RunStatus

SCHEMA_VERSION = "1.0"
AssayType = Literal["generic_grouped", "elisa_standard_curve"]
AnalysisLevel = Literal["measurement_rows"]
DescriptiveStatisticName = Literal[
    "n_measurements", "mean", "median", "min", "max", "sample_sd"
]


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
    "ValidationIssue",
]
