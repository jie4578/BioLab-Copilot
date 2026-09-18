"""Independent synthetic tests for the restricted Phase 3A 4PL workflow."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biolab_copilot.contracts import CurveFitResult, ELISA4PLDesign
from biolab_copilot.ingestion import read_source
from biolab_copilot.profiling import profile_and_validate
from biolab_copilot.statistics import (
    build_4pl_plan,
    compute_4pl_fit,
    four_pl_predict,
    validate_4pl_execution_inputs,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="phase3a-4pl-", dir=PROJECT_ROOT / "tests") as temp:
        yield Path(temp)


def _expected_increasing(x: float) -> float:
    return 0.1 + 2.0 * x / (10.0 + x)


def _expected_decreasing(x: float) -> float:
    return 0.1 + 2.0 * 10.0 / (10.0 + x)


def _rows(direction: str = "increasing") -> list[tuple[str, str, str, str, str, str, str]]:
    concentrations = ["0", "0.1", "0.3", "1", "3", "10", "30", "100", "300"]
    values = [
        _expected_increasing(float(x))
        if direction == "increasing"
        else _expected_decreasing(float(x))
        for x in concentrations
    ]
    return [
        (f"STD-{index}", "standard", concentration, repr(value), "ng/mL", "AU", f"R{index}")
        for index, (concentration, value) in enumerate(zip(concentrations, values, strict=True))
    ] + [("SAMPLE-1", "sample", "", "0.75", "ng/mL", "AU", "SAMPLE-R1")]


def _design(
    direction: str = "increasing", policy: str = "none"
) -> ELISA4PLDesign:
    return ELISA4PLDesign(
        curve_context_declared=True,
        curve_context_description="Synthetic single-curve standard context.",
        concentration_unit="ng/mL",
        response_unit="AU",
        direction=direction,  # type: ignore[arg-type]
        standard_replicate_policy=policy,  # type: ignore[arg-type]
        standard_repeat_id_field="replicate_id" if policy == "mean_by_concentration" else None,
    )


def _prepare(
    tmp_path: Path,
    rows: list[tuple[str, str, str, str, str, str, str]],
    *,
    direction: str = "increasing",
    policy: str = "none",
) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "source.csv"
    source.write_text(
        "sample_id,sample_type,standard_concentration,measurement,concentration_unit,measurement_unit,replicate_id\n"
        + "\n".join(",".join(row) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    mapping = {
        "sample_id": "sample_id",
        "sample_type": "sample_type",
        "standard_concentration": "standard_concentration",
        "measurement": "measurement",
        "concentration_unit": "concentration_unit",
        "measurement_unit": "measurement_unit",
        "replicate_id": "replicate_id",
    }
    imported = profile_and_validate(read_source(source), "elisa_standard_curve", mapping)
    artifact = tmp_path / "imported_data.json"
    artifact.write_text(imported.model_dump_json() + "\n", encoding="utf-8")
    design_path = tmp_path / "design.json"
    design_path.write_text(_design(direction, policy).model_dump_json() + "\n", encoding="utf-8")
    preview_path = tmp_path / "standards_preview.json"
    built = build_4pl_plan(artifact, design_path, preview_path)
    preview_path.write_text(built.preview.model_dump_json() + "\n", encoding="utf-8")
    plan = built.plan.model_copy(
        update={"standards_preview_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest()}
    )
    plan_path = tmp_path / "analysis_plan.json"
    plan_path.write_text(plan.model_dump_json() + "\n", encoding="utf-8")
    return artifact, design_path, plan_path


def _confirm(plan_path: Path) -> str:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["confirmed"] = True
    payload["warning_confirmations"] = {
        code: True for code in payload["required_confirmations"]
    }
    plan_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(plan_path.read_bytes()).hexdigest()


def test_four_pl_predictor_uses_declared_formula_and_zero_limits() -> None:
    assert four_pl_predict(0, 0.1, 2.1, 10, 1, "increasing") == pytest.approx(0.1)
    assert four_pl_predict(0, 0.1, 2.1, 10, 1, "decreasing") == pytest.approx(2.1)
    assert four_pl_predict(10, 0.1, 2.1, 10, 1, "increasing") == pytest.approx(1.1)
    assert four_pl_predict(10, 0.1, 2.1, 10, 1, "decreasing") == pytest.approx(1.1)


@pytest.mark.parametrize("direction", ["increasing", "decreasing"])
def test_noiseless_synthetic_curve_recovers_parameters(tmp_path: Path, direction: str) -> None:
    artifact, _, plan_path = _prepare(tmp_path, _rows(direction), direction=direction)
    original_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    plan_hash = _confirm(plan_path)
    preflight = validate_4pl_execution_inputs(plan_path, plan_hash, allowed_root=PROJECT_ROOT)
    result = compute_4pl_fit(preflight)

    assert result.status == "computed"
    assert result.lower_asymptote == pytest.approx(0.1, abs=1e-8)
    assert result.upper_asymptote == pytest.approx(2.1, abs=1e-8)
    assert result.midpoint_concentration == pytest.approx(10.0, abs=1e-7)
    assert result.slope_magnitude == pytest.approx(1.0, abs=1e-7)
    assert result.n_fit_levels == 9
    assert result.n_raw_standard_measurements == 9
    assert result.rmse == pytest.approx(0.0, abs=1e-10)
    assert result.curve_validated is False
    assert result.quantification_enabled is False
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == original_hash
    assert "NaN" not in result.model_dump_json()
    assert "Infinity" not in result.model_dump_json()


def test_row_order_does_not_change_fit_and_sample_is_excluded(tmp_path: Path) -> None:
    rows = _rows()
    artifact_a, _, plan_a = _prepare(tmp_path / "a", rows)
    artifact_b, _, plan_b = _prepare(tmp_path / "b", [*rows[:1], *reversed(rows[1:])])
    first = compute_4pl_fit(
        validate_4pl_execution_inputs(plan_a, _confirm(plan_a), allowed_root=PROJECT_ROOT)
    )
    second = compute_4pl_fit(
        validate_4pl_execution_inputs(plan_b, _confirm(plan_b), allowed_root=PROJECT_ROOT)
    )
    assert first.status == second.status == "computed"
    assert first.midpoint_concentration == pytest.approx(second.midpoint_concentration)
    assert first.sse == pytest.approx(second.sse)
    assert first.source_record_references["excluded_records"] == [10]
    assert second.source_record_references["excluded_records"] == [2]
    records_a = json.loads(artifact_a.read_text(encoding="utf-8"))["records"]
    records_b = json.loads(artifact_b.read_text(encoding="utf-8"))["records"]
    assert records_a[-1]["parsed_values"]["sample_type"] == "sample"
    assert records_b[-1]["parsed_values"]["sample_type"] == "standard"


def test_mean_by_concentration_is_level_weighted_and_warns_on_unequal_counts(
    tmp_path: Path,
) -> None:
    rows = _rows()[:]
    rows[1:1] = [
        (
            "STD-1-R2",
            "standard",
            "0.1",
            repr(_expected_increasing(0.1) + 0.02),
            "ng/mL",
            "AU",
            "R1-R2",
        ),
    ]
    artifact, _, plan_path = _prepare(
        tmp_path, rows, policy="mean_by_concentration"
    )
    plan_hash = _confirm(plan_path)
    preflight = validate_4pl_execution_inputs(plan_path, plan_hash, allowed_root=PROJECT_ROOT)
    result = compute_4pl_fit(preflight)
    assert result.status == "computed"
    assert result.n_fit_levels == 9
    assert result.n_raw_standard_measurements == 10
    level = next(point for point in result.fit_points if point.concentration == pytest.approx(0.1))
    assert level.n_measurements == 2
    assert any(issue.code == "UNEQUAL_STANDARD_REPLICATE_COUNTS" for issue in result.issues)
    assert json.loads(artifact.read_text(encoding="utf-8"))["input_file"]["sha256"]


def test_unconfirmed_or_changed_preview_is_rejected(tmp_path: Path) -> None:
    _, _, plan_path = _prepare(tmp_path, _rows())
    unconfirmed = validate_4pl_execution_inputs(
        plan_path,
        hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        allowed_root=PROJECT_ROOT,
    )
    assert any(issue.code == "PLAN_NOT_CONFIRMED" for issue in unconfirmed.issues)
    _confirm(plan_path)
    preview_path = tmp_path / "standards_preview.json"
    preview_path.write_text(preview_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    preflight = validate_4pl_execution_inputs(
        plan_path,
        hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        allowed_root=PROJECT_ROOT,
    )
    result = compute_4pl_fit(preflight)
    assert result.status == "failed"
    assert any(issue.code == "STANDARDS_PREVIEW_HASH_MISMATCH" for issue in result.issues)


@pytest.mark.parametrize(
    ("rows", "expected_code"),
    [
        (_rows()[:6], "INSUFFICIENT_POSITIVE_STANDARD_LEVELS"),
        (
            [
                (row[0], row[1], row[2], "1.0", row[4], row[5], row[6])
                for row in _rows()
            ],
            "CONSTANT_STANDARD_RESPONSE",
        ),
        (
            [
                (
                    _rows()[0][0],
                    _rows()[1][1],
                    "-1",
                    _rows()[1][3],
                    "ng/mL",
                    "AU",
                    "RNEG",
                )
            ]
            + _rows()[1:],
            "NEGATIVE_STANDARD_CONCENTRATION",
        ),
    ],
)
def test_invalid_standard_inputs_are_blocked(
    tmp_path: Path,
    rows: list[tuple[str, str, str, str, str, str, str]],
    expected_code: str,
) -> None:
    _, _, plan_path = _prepare(tmp_path, rows)
    plan_hash = _confirm(plan_path)
    preflight = validate_4pl_execution_inputs(plan_path, plan_hash, allowed_root=PROJECT_ROOT)
    assert any(issue.code == expected_code for issue in preflight.issues)


def test_synthetic_expected_values_do_not_call_fit_predictor() -> None:
    expected = [_expected_increasing(x) for x in [0.1, 1.0, 10.0, 100.0]]
    assert expected == pytest.approx(
        [0.1198019801980198, 0.2818181818181818, 1.1, 1.918181818181818]
    )
    assert math.isfinite(expected[0])


def test_phase3a_contracts_round_trip_schema_and_extra_field_rejection() -> None:
    design = _design()
    restored = ELISA4PLDesign.model_validate_json(design.model_dump_json())
    assert restored == design
    assert "properties" in CurveFitResult.model_json_schema()
    with pytest.raises(ValueError):
        ELISA4PLDesign.model_validate({**design.model_dump(), "unapproved": True})
