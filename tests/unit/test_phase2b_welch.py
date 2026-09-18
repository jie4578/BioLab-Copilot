"""Phase 2B unit-level Welch tests with independent expected values."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import pytest
from scipy import stats

from biolab_copilot.contracts import ImportResult, IndependentTwoGroupDesign
from biolab_copilot.ingestion import read_source
from biolab_copilot.profiling import profile_and_validate
from biolab_copilot.statistics import (
    build_analysis_plan,
    build_welch_plan,
    compute_welch_result,
    validate_welch_execution_inputs,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="phase2b-stats-", dir=PROJECT_ROOT / "tests") as temp:
        yield Path(temp)


def _design(
    *,
    technical_repeat_policy: Literal["none", "mean"] = "none",
    group_a: str = "A",
    group_b: str = "B",
) -> IndependentTwoGroupDesign:
    return IndependentTwoGroupDesign(
        design_type="independent_two_group",
        experimental_unit_description="One explicitly identified independent experimental unit.",
        experimental_unit_id_field="experimental_unit_id",
        independence_declared=True,
        independence_rationale="The user declares that the two groups contain independent units.",
        group_a=group_a,
        group_b=group_b,
        technical_repeat_policy=technical_repeat_policy,
        method="welch_t",
        alternative="two-sided",
        alpha=0.05,
        confidence_level=0.95,
        assumptions_acknowledged=True,
    )


def _make_import(
    tmp_path: Path,
    rows: list[tuple[str, str, float, str, str, str]],
    *,
    experiment_type: str = "generic_grouped",
) -> tuple[ImportResult, Path]:
    source = tmp_path / "source.csv"
    source.write_text(
        "sample_id,group,measurement,experimental_unit_id,replicate_type,technical_replicate_id\n"
        + "\n".join(",".join(map(str, row)) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    mapping = {
        "sample_id": "sample_id",
        "group": "group",
        "measurement": "measurement",
        "experimental_unit_id": "experimental_unit_id",
        "replicate_type": "replicate_type",
        "technical_replicate_id": "technical_replicate_id",
    }
    result = profile_and_validate(read_source(source), experiment_type, mapping)
    artifact = tmp_path / "imported_data.json"
    artifact.write_text(result.model_dump_json() + "\n", encoding="utf-8")
    return result, artifact


def _prepare_plan(
    tmp_path: Path,
    rows: list[tuple[str, str, float, str, str, str]],
    *,
    design: IndependentTwoGroupDesign | None = None,
) -> tuple[ImportResult, Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    import_result, artifact = _make_import(tmp_path, rows)
    design = design or _design()
    design_path = tmp_path / "design.json"
    design_path.write_text(design.model_dump_json() + "\n", encoding="utf-8")
    preview_path = tmp_path / "experimental_units.json"
    built = build_welch_plan(artifact, design_path, preview_path)
    preview_path.write_text(
        built.preview.model_dump_json() + "\n", encoding="utf-8"
    )
    plan = built.plan.model_copy(
        update={"preview_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest()}
    )
    plan_path = tmp_path / "analysis_plan.json"
    plan_path.write_text(plan.model_dump_json() + "\n", encoding="utf-8")
    return import_result, artifact, design_path, plan_path


def _confirm(plan_path: Path) -> str:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["confirmed"] = True
    payload["warning_confirmations"] = {
        code: True for code in payload["required_confirmations"]
    }
    plan_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(plan_path.read_bytes()).hexdigest()


def test_fixed_welch_values_and_independent_ci_expectations(tmp_path: Path) -> None:
    _, _, _, plan_path = _prepare_plan(
        tmp_path,
        [
            ("A1", "A", 1, "U-A1", "biological", ""),
            ("A2", "A", 2, "U-A2", "biological", ""),
            ("A3", "A", 3, "U-A3", "biological", ""),
            ("B1", "B", 4, "U-B1", "biological", ""),
            ("B2", "B", 5, "U-B2", "biological", ""),
            ("B3", "B", 6, "U-B3", "biological", ""),
        ],
    )
    plan_hash = _confirm(plan_path)
    preflight = validate_welch_execution_inputs(plan_path, plan_hash)
    result = compute_welch_result(preflight)

    assert result.status == "computed"
    assert result.mean_difference == pytest.approx(-3)
    assert [group.sample_sd for group in result.inferential_group_statistics] == [1, 1]
    assert result.t_statistic == pytest.approx(-3 / math.sqrt(2 / 3))
    assert result.degrees_of_freedom == pytest.approx(4)
    standard_error = math.sqrt(1 / 3 + 1 / 3)
    critical = stats.t.ppf(0.975, 4)
    assert result.mean_difference_ci_lower == pytest.approx(-3 - critical * standard_error)
    assert result.mean_difference_ci_upper == pytest.approx(-3 + critical * standard_error)
    assert result.p_value == pytest.approx(0.021311641128756727)
    assert result.independence_status == "user_declared_not_verified"
    assert result.independent_biological_n is None
    assert "NaN" not in result.model_dump_json()
    assert "Infinity" not in result.model_dump_json()


def test_swapping_groups_reverses_difference_and_t_but_not_two_sided_p(tmp_path: Path) -> None:
    rows = [
        ("A1", "A", 1, "U-A1", "biological", ""),
        ("A2", "A", 2, "U-A2", "biological", ""),
        ("A3", "A", 3, "U-A3", "biological", ""),
        ("B1", "B", 4, "U-B1", "biological", ""),
        ("B2", "B", 5, "U-B2", "biological", ""),
        ("B3", "B", 6, "U-B3", "biological", ""),
    ]
    _, _, _, first_plan = _prepare_plan(tmp_path / "first", rows)
    _, _, _, second_plan = _prepare_plan(
        tmp_path / "second", rows, design=_design(group_a="B", group_b="A")
    )
    first_hash = _confirm(first_plan)
    second_hash = _confirm(second_plan)
    first = compute_welch_result(validate_welch_execution_inputs(first_plan, first_hash))
    second = compute_welch_result(validate_welch_execution_inputs(second_plan, second_hash))

    assert second.mean_difference == pytest.approx(-first.mean_difference)
    assert second.t_statistic == pytest.approx(-first.t_statistic)
    assert second.p_value == pytest.approx(first.p_value)
    assert second.mean_difference_ci_lower == pytest.approx(-first.mean_difference_ci_upper)
    assert second.mean_difference_ci_upper == pytest.approx(-first.mean_difference_ci_lower)


def test_mean_policy_aggregates_technical_repeats_equal_by_unit(tmp_path: Path) -> None:
    rows = [
        ("A1-r1", "A", 1, "U-A1", "technical", "r1"),
        ("A1-r2", "A", 3, "U-A1", "technical", "r2"),
        ("A2-r1", "A", 2.5, "U-A2", "technical", "r1"),
        ("B1-r1", "B", 4, "U-B1", "technical", "r1"),
        ("B2-r1", "B", 5, "U-B2", "technical", "r1"),
    ]
    _, _, _, plan_path = _prepare_plan(
        tmp_path, rows, design=_design(technical_repeat_policy="mean")
    )
    plan_hash = _confirm(plan_path)
    preflight = validate_welch_execution_inputs(plan_path, plan_hash)
    result = compute_welch_result(preflight)

    assert result.status == "computed"
    assert [unit.aggregated_value for unit in result.experimental_unit_summaries] == [2, 2.5, 4, 5]
    assert [group.n_measurements for group in result.inferential_group_statistics] == [3, 2]
    assert [group.n_experimental_units for group in result.inferential_group_statistics] == [2, 2]
    assert any(issue.code == "TECHNICAL_REPLICATE_COUNT_DIFFERS" for issue in result.issues)


def test_unit_identity_and_repeat_policy_block_inference_without_cleaning(tmp_path: Path) -> None:
    rows = [
        ("A1-r1", "A", 1, "U1", "biological", ""),
        ("A1-r2", "A", 2, "U1", "biological", ""),
        ("A2", "A", 3, "U2", "biological", ""),
        ("B1", "B", 4, "U3", "biological", ""),
        ("B2", "B", 5, "U4", "biological", ""),
    ]
    _, _, _, plan_path = _prepare_plan(tmp_path, rows)
    plan_hash = _confirm(plan_path)
    preflight = validate_welch_execution_inputs(plan_path, plan_hash)
    result = compute_welch_result(preflight)

    assert result.status == "failed"
    assert any(
        issue.code == "MULTIPLE_MEASUREMENTS_PER_UNIT_NONE_POLICY"
        for issue in result.issues
    )
    assert len(preflight.preview.units) == 3
    assert len(preflight.preview.rows) == 5


def test_cross_group_unit_missing_unit_and_zero_variance_are_blocked(tmp_path: Path) -> None:
    cross_rows = [
        ("A1", "A", 1, "CROSS", "biological", ""),
        ("A2", "A", 2, "U-A2", "biological", ""),
        ("B1", "B", 4, "CROSS", "biological", ""),
        ("B2", "B", 5, "U-B2", "biological", ""),
    ]
    _, _, _, cross_plan = _prepare_plan(tmp_path / "cross", cross_rows)
    cross_hash = _confirm(cross_plan)
    cross_result = compute_welch_result(
        validate_welch_execution_inputs(cross_plan, cross_hash)
    )
    assert cross_result.status == "failed"
    assert any(issue.code == "EXPERIMENTAL_UNIT_CROSSES_GROUPS" for issue in cross_result.issues)

    missing_rows = [
        ("A1", "A", 1, "", "biological", ""),
        ("A2", "A", 2, "U-A2", "biological", ""),
        ("B1", "B", 4, "U-B1", "biological", ""),
        ("B2", "B", 5, "U-B2", "biological", ""),
    ]
    _, _, _, missing_plan = _prepare_plan(tmp_path / "missing", missing_rows)
    missing_hash = _confirm(missing_plan)
    missing_result = compute_welch_result(
        validate_welch_execution_inputs(missing_plan, missing_hash)
    )
    assert missing_result.status == "failed"
    assert any(issue.code == "EXPERIMENTAL_UNIT_ID_MISSING" for issue in missing_result.issues)

    zero_rows = [
        ("A1", "A", 1, "U-A1", "biological", ""),
        ("A2", "A", 1, "U-A2", "biological", ""),
        ("B1", "B", 2, "U-B1", "biological", ""),
        ("B2", "B", 2, "U-B2", "biological", ""),
    ]
    _, _, _, zero_plan = _prepare_plan(tmp_path / "zero", zero_rows)
    zero_hash = _confirm(zero_plan)
    zero_result = compute_welch_result(validate_welch_execution_inputs(zero_plan, zero_hash))
    assert zero_result.status == "failed"
    assert any(issue.code == "BOTH_GROUPS_ZERO_VARIANCE" for issue in zero_result.issues)


def test_plan_confirmation_and_bindings_are_not_bypassable(tmp_path: Path) -> None:
    _, artifact, design_path, plan_path = _prepare_plan(
        tmp_path,
        [
            ("A1", "A", 1, "U-A1", "biological", ""),
            ("A2", "A", 2, "U-A2", "biological", ""),
            ("B1", "B", 4, "U-B1", "biological", ""),
            ("B2", "B", 5, "U-B2", "biological", ""),
        ],
    )
    original_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    assert compute_welch_result(
        validate_welch_execution_inputs(plan_path, original_hash)
    ).status == "failed"
    assert any(
        issue.code == "PLAN_NOT_CONFIRMED"
        for issue in validate_welch_execution_inputs(plan_path, original_hash).issues
    )

    _confirm(plan_path)
    design_path.write_text(design_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed_design = compute_welch_result(
        validate_welch_execution_inputs(
            plan_path, hashlib.sha256(plan_path.read_bytes()).hexdigest()
        )
    )
    assert changed_design.status == "failed"
    assert any(
        issue.code == "DESIGN_DECLARATION_HASH_MISMATCH" for issue in changed_design.issues
    )

    assert artifact.is_file()


def test_phase2a_plan_cannot_be_used_for_phase2b(tmp_path: Path) -> None:
    _, artifact = _make_import(
        tmp_path,
        [
            ("A1", "A", 1, "U-A1", "biological", ""),
            ("B1", "B", 2, "U-B1", "biological", ""),
        ],
    )
    phase2a_plan = build_analysis_plan(artifact, ImportResult.model_validate_json(
        artifact.read_text(encoding="utf-8")
    ))
    plan_path = tmp_path / "phase2a-plan.json"
    plan_path.write_text(phase2a_plan.model_dump_json() + "\n", encoding="utf-8")
    preflight = validate_welch_execution_inputs(
        plan_path, hashlib.sha256(plan_path.read_bytes()).hexdigest()
    )
    assert any(issue.code == "UNSUPPORTED_PHASE2B_PLAN_LEVEL" for issue in preflight.issues)
