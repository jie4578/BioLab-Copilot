"""Independent numerical and contract tests for Phase 3B inverse estimation."""

from __future__ import annotations

import json
import math

from biolab_copilot.contracts import (
    CurveFitResult,
    DatasetProfile,
    ELISAInverseDesign,
    ImportedRecord,
    ImportResult,
    InputFile,
)
from biolab_copilot.statistics.elisa_inverse import (
    _build_sample_preview,
    _inverse_one,
)


def _curve(direction: str) -> CurveFitResult:
    return CurveFitResult(
        result_id="curve-1",
        experiment_id="synthetic",
        plan_id="plan-curve-1",
        status="computed",
        direction=direction,  # type: ignore[arg-type]
        concentration_unit="ng/mL",
        response_unit="AU",
        lower_asymptote=0.1,
        upper_asymptote=2.1,
        midpoint_concentration=10.0,
        slope_magnitude=1.0,
        convergence_status="converged_candidate_selected",
        observed_standard_concentration_span=(1.0, 100.0),
        curve_validated=False,
        quantification_enabled=False,
    )


def _design(factor: float = 1.0) -> ELISAInverseDesign:
    return ELISAInverseDesign(
        research_only_acknowledged=True,
        curve_context_compatibility_declared=True,
        curve_context_compatibility_rationale=(
            "Synthetic source and response scale are explicitly declared compatible for "
            "research use."
        ),
        sample_source_mode="same_import_artifact",
        dilution_factor_source="uniform_declared",
        uniform_dilution_factor=factor,
    )


def _increasing_response(x: float) -> float:
    return 0.1 + 2.0 * x / (10.0 + x)


def _decreasing_response(x: float) -> float:
    return 0.1 + 2.0 * 10.0 / (10.0 + x)


def test_inverse_recovers_known_values_for_both_directions() -> None:
    for direction, response_function in (
        ("increasing", _increasing_response),
        ("decreasing", _decreasing_response),
    ):
        curve = _curve(direction)
        for expected in (1.0, 3.0, 10.0, 30.0, 100.0):
            status, assayed, original, _ = _inverse_one(
                response_function(expected),
                1.0,
                curve,
                _design(),
                (1.0, 100.0),
                (0.1 + 2.0 / 11.0, 0.1 + 200.0 / 110.0),
            )
            assert status == "estimated_within_standard_span"
            assert assayed is not None and math.isclose(assayed, expected, rel_tol=1e-12)
            assert original is not None and math.isclose(original, expected, rel_tol=1e-12)


def test_inverse_uses_direction_for_span_classification_and_dilution() -> None:
    for direction, response_function in (
        ("increasing", _increasing_response),
        ("decreasing", _decreasing_response),
    ):
        curve = _curve(direction)
        response_span = (0.1 + 2.0 / 11.0, 0.1 + 200.0 / 110.0)
        below = _inverse_one(
            response_function(0.1), 10.0, curve, _design(10.0), (1.0, 100.0), response_span
        )
        above = _inverse_one(
            response_function(1000.0), 10.0, curve, _design(10.0), (1.0, 100.0), response_span
        )
        assert below[0] == "below_standard_span"
        assert above[0] == "above_standard_span"
        assert below[1:] == (None, None, below[3])
        assert above[1:] == (None, None, above[3])
        within = _inverse_one(
            response_function(3.0), 10.0, curve, _design(10.0), (1.0, 100.0), response_span
        )
        assert within[0] == "estimated_within_standard_span"
        assert math.isclose(within[2] or 0.0, 30.0, rel_tol=1e-12)


def test_asymptotes_and_domain_never_produce_a_concentration() -> None:
    curve = _curve("increasing")
    response_span = (0.1 + 2.0 / 11.0, 0.1 + 200.0 / 110.0)
    for response, expected_status in (
        (0.1, "near_asymptote_unstable"),
        (2.1, "near_asymptote_unstable"),
        (0.1 - 1e-3, "outside_model_domain"),
        (2.1 + 1e-3, "outside_model_domain"),
    ):
        result = _inverse_one(response, 1.0, curve, _design(), (1.0, 100.0), response_span)
        assert result[0] == expected_status
        assert result[1] is None and result[2] is None


def _import_result() -> ImportResult:
    records = [
        ImportedRecord(
            record_number=1,
            source_file="synthetic.csv",
            raw_values={"sample_id": "S-1", "sample_type": "sample", "measurement": "0.5"},
            parsed_values={
                "sample_id": "S-1",
                "sample_type": "sample",
                "measurement": 0.5,
                "replicate_type": "technical",
                "replicate_id": "T1",
            },
            source_locations={"measurement": "file=synthetic.csv; record=1; column='measurement'"},
        ),
        ImportedRecord(
            record_number=2,
            source_file="synthetic.csv",
            raw_values={"sample_id": "S-1", "sample_type": "sample", "measurement": "0.5"},
            parsed_values={
                "sample_id": "S-1",
                "sample_type": "sample",
                "measurement": 0.5,
                "replicate_type": "technical",
                "replicate_id": "T2",
            },
            source_locations={"measurement": "file=synthetic.csv; record=2; column='measurement'"},
        ),
        ImportedRecord(
            record_number=3,
            source_file="synthetic.csv",
            raw_values={"sample_id": "STD-1", "sample_type": "standard", "measurement": "0.2"},
            parsed_values={"sample_id": "STD-1", "sample_type": "standard", "measurement": 0.2},
            source_locations={"measurement": "file=synthetic.csv; record=3; column='measurement'"},
        ),
    ]
    return ImportResult(
        input_file=InputFile(path="C:/project/source.csv", sha256="a" * 64, size_bytes=1),
        experiment_type="elisa_standard_curve",
        column_mapping={"measurement": "measurement"},
        parse_configuration={"encoding": "utf-8-sig", "delimiter": ","},
        dataset_profile=DatasetProfile(
            dataset_id="synthetic",
            source_filename="source.csv",
            source_sha256="a" * 64,
            row_count=3,
            column_count=3,
            column_names=["sample_id", "sample_type", "measurement"],
            missing_value_count=0,
        ),
        records=records,
        analysis_ready=True,
    )


def test_preview_keeps_duplicate_sample_measurements_and_excludes_non_samples() -> None:
    curve = _curve("increasing")
    preview, issues, blockers = _build_sample_preview(
        curve,
        _import_result(),
        _design(),
        curve_result_sha256="b" * 64,
        sample_artifact_sha256="c" * 64,
    )
    assert not blockers
    assert not issues
    assert len(preview.records) == 2
    assert [item.record_number for item in preview.records] == [1, 2]
    assert [item.record_number for item in preview.excluded_records] == [3]


def test_design_requires_explicit_dilution_and_research_acknowledgement() -> None:
    try:
        ELISAInverseDesign(
            research_only_acknowledged=True,
            curve_context_compatibility_declared=True,
            curve_context_compatibility_rationale="declared",
            sample_source_mode="same_import_artifact",
            dilution_factor_source="uniform_declared",
        )
    except ValueError as exc:
        assert "uniform_dilution_factor" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("missing dilution factor must be rejected")


def test_missing_mapped_dilution_is_an_error_and_never_defaults_to_one() -> None:
    mapped = _design().model_copy(
        update={
            "dilution_factor_source": "mapped_field",
            "dilution_factor_field": "dilution_factor",
            "uniform_dilution_factor": None,
        }
    )
    preview, issues, _ = _build_sample_preview(
        _curve("increasing"),
        _import_result(),
        mapped,
        curve_result_sha256="b" * 64,
        sample_artifact_sha256="c" * 64,
    )
    assert len(preview.records) == 2
    assert all(item.status == "numerical_failure" for item in preview.records)
    assert all(item.dilution_factor is None for item in preview.records)
    assert any(issue.code == "DILUTION_FACTOR_INVALID" for issue in issues)


def test_inverse_contract_serialization_is_strict_json() -> None:
    payload = _build_sample_preview(
        _curve("increasing"),
        _import_result(),
        _design(),
        curve_result_sha256="b" * 64,
        sample_artifact_sha256="c" * 64,
    )[0].model_dump(mode="json")
    encoded = json.dumps(payload, allow_nan=False)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
