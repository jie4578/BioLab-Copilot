"""Unit tests for Phase 0 contracts only."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from biolab_copilot.contracts import (
    AnalysisPlan,
    AnalysisResult,
    ChartArtifact,
    DatasetProfile,
    ExperimentSpec,
    ReportArtifact,
    RunManifest,
    RunStatus,
    StatisticRecord,
    ValidationIssue,
)

SHA256 = "a" * 64


def test_experiment_spec_round_trips_and_exports_schema() -> None:
    model = ExperimentSpec(
        experiment_id="exp-001",
        name="Synthetic grouped assay",
        assay_type="generic_grouped",
        source_filename="generic_normal.csv",
        configuration={"measurement_column": "measurement"},
    )

    restored = ExperimentSpec.model_validate_json(model.model_dump_json())

    assert restored == model
    assert model.model_json_schema()["properties"]["schema_version"]["default"] == "1.0"


def test_all_phase_zero_models_support_json_round_trip() -> None:
    issue = ValidationIssue(
        code="MISSING_VALUE",
        severity="warning",
        message="One synthetic value is missing.",
        location="measurement[row=2]",
        suggested_action="Review the source record; do not delete it automatically.",
    )
    plan = AnalysisPlan(
        plan_id="plan-001",
        experiment_id="exp-001",
        assay_type="generic_grouped",
        objectives=["Describe group measurements"],
    )
    result = AnalysisResult(
        result_id="result-001",
        experiment_id="exp-001",
        plan_id="plan-001",
        status="computed",
        statistics=[StatisticRecord(name="mean", value=1.5, group="control")],
        issues=[issue],
    )
    chart = ChartArtifact(
        artifact_id="chart-001",
        result_id="result-001",
        chart_type="placeholder",
        title="Synthetic chart metadata",
        path="artifacts/chart-001.png",
        mime_type="image/png",
        source_data_sha256=SHA256,
    )
    report = ReportArtifact(
        artifact_id="report-001",
        run_id="run-001",
        report_type="json",
        path="artifacts/report-001.json",
        mime_type="application/json",
        source_manifest_sha256=SHA256,
    )
    profile = DatasetProfile(
        dataset_id="dataset-001",
        source_filename="generic_normal.csv",
        source_sha256=SHA256,
        row_count=4,
        column_count=4,
        column_names=["sample_id", "group", "measurement", "replicate"],
        missing_value_count=0,
    )
    manifest = RunManifest(
        run_id="run-001",
        experiment_id="exp-001",
        status=RunStatus.CREATED,
        created_at=datetime.now(UTC),
        warnings=[issue],
    )

    for model in (issue, plan, result, chart, report, profile, manifest):
        restored = type(model).model_validate_json(model.model_dump_json())
        assert restored == model
        assert "schema_version" in type(model).model_json_schema()["properties"]


def test_invalid_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ExperimentSpec(
            experiment_id="exp-001",
            name="Invalid assay",
            assay_type="unsupported_assay",
            source_filename="input.csv",
        )

    with pytest.raises(ValidationError):
        DatasetProfile(
            dataset_id="dataset-001",
            source_filename="input.csv",
            source_sha256="not-a-sha256",
            row_count=1,
            column_count=1,
            missing_value_count=0,
        )

    with pytest.raises(ValidationError):
        ValidationIssue(
            code="UNKNOWN",
            severity="fatal",
            message="Invalid severity.",
            location="dataset",
            suggested_action="Reject.",
        )


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ExperimentSpec(
            experiment_id="exp-001",
            name="Extra field",
            assay_type="generic_grouped",
            source_filename="input.csv",
            unexpected_value=True,
        )


def test_run_status_contains_required_lifecycle_values() -> None:
    assert {status.value for status in RunStatus} == {
        "CREATED",
        "VALIDATING",
        "NEEDS_CONFIRMATION",
        "READY",
        "ANALYZING",
        "REPORTING",
        "COMPLETED",
        "PARTIAL",
        "FAILED",
    }
