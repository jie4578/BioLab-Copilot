"""Phase 2A deterministic descriptive-statistics tests with independent expectations."""

from __future__ import annotations

import math
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biolab_copilot.contracts import AnalysisPlan, ImportResult
from biolab_copilot.ingestion import read_source
from biolab_copilot.profiling import profile_and_validate
from biolab_copilot.statistics import build_analysis_plan, compute_grouped_descriptive

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="phase2a-stats-", dir=PROJECT_ROOT / "tests") as temp:
        yield Path(temp)


def _make_import_and_plan(
    tmp_path: Path,
    rows: list[tuple[str, str, float]],
    *,
    replicate_type: str = "biological",
) -> tuple[ImportResult, AnalysisPlan]:
    source = tmp_path / "generic.csv"
    content = "sample_id,group,measurement,replicate_type\n" + "\n".join(
        f"{sample_id},{group},{measurement},{replicate_type}"
        for sample_id, group, measurement in rows
    )
    source.write_text(content + "\n", encoding="utf-8")
    import_result = profile_and_validate(
        read_source(source),
        "generic_grouped",
        {
            "sample_id": "sample_id",
            "group": "group",
            "measurement": "measurement",
            "replicate_type": "replicate_type",
        },
    )
    artifact = tmp_path / "imported_data.json"
    artifact.write_text(import_result.model_dump_json(), encoding="utf-8")
    return import_result, build_analysis_plan(artifact, import_result)


def _confirmed(plan: AnalysisPlan) -> AnalysisPlan:
    return plan.model_copy(
        update={
            "confirmed": True,
            "warning_confirmations": {
                code: True for code in plan.required_confirmations
            },
        }
    )


def test_fixed_values_1_2_3_have_expected_descriptive_statistics(tmp_path: Path) -> None:
    import_result, plan = _make_import_and_plan(
        tmp_path,
        [("S1", "control", 1), ("S2", "control", 2), ("S3", "control", 3)],
    )

    result = compute_grouped_descriptive(import_result, _confirmed(plan), "a" * 64)
    stats = result.group_statistics[0]

    assert result.status == "computed"
    assert stats.n_measurements == 3
    assert stats.mean == 2
    assert stats.median == 2
    assert stats.min == 1
    assert stats.max == 3
    assert stats.sample_sd == 1
    assert stats.source_record_numbers == [1, 2, 3]
    assert result.independent_biological_n is None


def test_constant_values_have_zero_sample_sd(tmp_path: Path) -> None:
    import_result, plan = _make_import_and_plan(
        tmp_path,
        [("S1", "control", 4), ("S2", "control", 4), ("S3", "control", 4)],
    )

    stats = compute_grouped_descriptive(
        import_result, _confirmed(plan), "b" * 64
    ).group_statistics[0]

    assert stats.sample_sd == 0


def test_two_values_have_independent_median_and_sample_sd_expectations(tmp_path: Path) -> None:
    import_result, plan = _make_import_and_plan(
        tmp_path,
        [("S1", "control", 1), ("S2", "control", 3)],
    )

    stats = compute_grouped_descriptive(
        import_result, _confirmed(plan), "c" * 64
    ).group_statistics[0]

    assert stats.median == 2
    assert stats.sample_sd == math.sqrt(2)


def test_single_measurement_returns_null_sample_sd_with_reason(tmp_path: Path) -> None:
    import_result, plan = _make_import_and_plan(tmp_path, [("S1", "control", 7)])

    stats = compute_grouped_descriptive(
        import_result, _confirmed(plan), "d" * 64
    ).group_statistics[0]

    assert stats.n_measurements == 1
    assert stats.mean == 7
    assert stats.median == 7
    assert stats.min == 7
    assert stats.max == 7
    assert stats.sample_sd is None
    assert stats.sample_sd_reason == "sample_sd requires at least two measurement rows (ddof=1)."


def test_negative_zero_multiple_groups_and_source_references_are_preserved(tmp_path: Path) -> None:
    import_result, plan = _make_import_and_plan(
        tmp_path,
        [
            ("S1", "control", -2),
            ("S2", "control", 0),
            ("S3", "treatment", 2),
        ],
    )

    result = compute_grouped_descriptive(import_result, _confirmed(plan), "e" * 64)
    by_group = {stats.group: stats for stats in result.group_statistics}

    assert by_group["control"].mean == -1
    assert by_group["control"].min == -2
    assert by_group["control"].max == 0
    assert by_group["treatment"].mean == 2
    assert result.source_record_references == {"control": [1, 2], "treatment": [3]}


def test_duplicate_rows_and_technical_repeats_are_not_aggregated(tmp_path: Path) -> None:
    source = tmp_path / "repeated.csv"
    source.write_text(
        "sample_id,group,measurement,replicate_type\nS1,control,1,technical\n"
        "S1,control,1,technical\n",
        encoding="utf-8",
    )
    import_result = profile_and_validate(
        read_source(source),
        "generic_grouped",
        {
            "sample_id": "sample_id",
            "group": "group",
            "measurement": "measurement",
            "replicate_type": "replicate_type",
        },
    )
    artifact = tmp_path / "repeated_imported_data.json"
    artifact.write_text(import_result.model_dump_json(), encoding="utf-8")
    plan = _confirmed(build_analysis_plan(artifact, import_result))

    result = compute_grouped_descriptive(import_result, plan, "f" * 64)

    assert len(import_result.records) == 2
    assert result.group_statistics[0].n_measurements == 2
    assert result.group_statistics[0].source_record_numbers == [1, 2]
    assert result.independent_biological_n is None
    assert any(issue.code == "DUPLICATE_COMPLETE_RECORD" for issue in result.issues)


def test_unknown_repeat_type_remains_a_warning_and_never_creates_biological_n(
    tmp_path: Path,
) -> None:
    import_result, plan = _make_import_and_plan(
        tmp_path,
        [("S1", "control", 1), ("S2", "control", 2)],
        replicate_type="unknown",
    )

    result = compute_grouped_descriptive(import_result, _confirmed(plan), "1" * 64)

    assert result.status == "computed"
    assert result.independent_biological_n is None
    assert any(issue.code == "REPLICATE_TYPE_UNKNOWN" for issue in result.issues)


def test_extreme_finite_values_that_overflow_fail_without_successful_statistics(
    tmp_path: Path,
) -> None:
    import_result, plan = _make_import_and_plan(
        tmp_path,
        [("S1", "control", 1e308), ("S2", "control", 1e308)],
    )

    result = compute_grouped_descriptive(import_result, _confirmed(plan), "2" * 64)

    assert result.status == "failed"
    assert result.group_statistics == []
    assert any(issue.code == "NON_FINITE_STATISTIC" for issue in result.issues)
    serialized = result.model_dump_json()
    assert "NaN" not in serialized
    assert "Infinity" not in serialized
