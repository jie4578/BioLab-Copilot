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
    GroupDescriptiveStats,
    IndependentTwoGroupDesign,
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


def test_phase2a_contracts_round_trip_and_reject_non_finite_group_values() -> None:
    stats = GroupDescriptiveStats(
        group="control",
        n_measurements=2,
        mean=2.0,
        median=2.0,
        min=1.0,
        max=3.0,
        sample_sd=2**0.5,
        source_record_numbers=[1, 2],
    )
    plan = AnalysisPlan(
        plan_id="plan-001",
        experiment_id="exp-001",
        assay_type="generic_grouped",
        objectives=["Describe preserved measurement rows."],
        analysis_level="measurement_rows",
        statistics=["n_measurements", "mean", "median", "min", "max", "sample_sd"],
        sample_sd_ddof=1,
        duplicate_record_policy="retain_and_include_all",
        required_confirmations=["DUPLICATE_COMPLETE_RECORD"],
        warning_confirmations={"DUPLICATE_COMPLETE_RECORD": True},
        confirmed=True,
        input_artifact_sha256=SHA256,
        source_sha256=SHA256,
    )

    assert GroupDescriptiveStats.model_validate_json(stats.model_dump_json()) == stats
    assert AnalysisPlan.model_validate_json(plan.model_dump_json()) == plan
    assert "group_statistics" in AnalysisResult.model_json_schema()["properties"]

    with pytest.raises(ValidationError):
        GroupDescriptiveStats(
            group="control",
            n_measurements=2,
            mean=float("nan"),
            median=2.0,
            min=1.0,
            max=3.0,
            source_record_numbers=[1, 2],
        )


def test_phase2b_design_contract_is_explicit_and_phase2a_plan_remains_compatible() -> None:
    design = IndependentTwoGroupDesign(
        design_type="independent_two_group",
        experimental_unit_description="One explicitly identified unit.",
        experimental_unit_id_field="experimental_unit_id",
        independence_declared=True,
        independence_rationale="The user declares independent units.",
        group_a="A",
        group_b="B",
        technical_repeat_policy="none",
        method="welch_t",
        alternative="two-sided",
        alpha=0.05,
        confidence_level=0.95,
        assumptions_acknowledged=True,
    )
    assert IndependentTwoGroupDesign.model_validate_json(design.model_dump_json()) == design
    schema = IndependentTwoGroupDesign.model_json_schema()
    assert "experimental_unit_id_field" in schema["properties"]

    phase2a_plan = AnalysisPlan(
        plan_id="phase2a-plan",
        experiment_id="exp-001",
        assay_type="generic_grouped",
        objectives=["Describe rows"],
        analysis_level="measurement_rows",
        statistics=["n_measurements", "mean", "median", "min", "max", "sample_sd"],
    )
    assert AnalysisPlan.model_validate_json(phase2a_plan.model_dump_json()) == phase2a_plan

    with pytest.raises(ValidationError):
        IndependentTwoGroupDesign(
            **design.model_dump(exclude={"group_b"}),
            group_b="A",
        )
    with pytest.raises(ValidationError):
        IndependentTwoGroupDesign(
            **design.model_dump(exclude={"alpha"}),
            alpha=0.01,
        )
