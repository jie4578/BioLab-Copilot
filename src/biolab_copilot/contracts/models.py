"""Versioned Pydantic contracts for BioLab Copilot.

This module intentionally contains schemas and validation only. It does not read files,
clean data, calculate statistics, call an LLM, or render reports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import IssueSeverity, RunStatus

SCHEMA_VERSION = "1.0"
AssayType = Literal["generic_grouped", "elisa_standard_curve"]


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


class ValidationIssue(ContractBaseModel):
    """A reviewable validation or QC finding."""

    code: str = Field(min_length=1)
    severity: IssueSeverity
    message: str = Field(min_length=1)
    location: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    auto_fixed: bool = False


class AnalysisPlan(ContractBaseModel):
    """An explicit plan awaiting or following user confirmation."""

    plan_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    assay_type: AssayType
    objectives: list[str] = Field(min_length=1)
    requested_outputs: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class StatisticRecord(ContractBaseModel):
    """A structured statistic produced by deterministic software in a later phase."""

    name: str = Field(min_length=1)
    value: float | int | None = None
    unit: str | None = None
    group: str | None = None
    method: str | None = None


class AnalysisResult(ContractBaseModel):
    """Structured analysis output; no narrative or LLM-generated values."""

    result_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: Literal["computed", "partial", "failed"]
    statistics: list[StatisticRecord] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


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


__all__ = [
    "SCHEMA_VERSION",
    "AnalysisPlan",
    "AnalysisResult",
    "AssayType",
    "ChartArtifact",
    "ContractBaseModel",
    "DatasetProfile",
    "ExperimentSpec",
    "InputFile",
    "ReportArtifact",
    "RunManifest",
    "StatisticRecord",
    "ValidationIssue",
]
