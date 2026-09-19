"""Contract and deterministic-artifact tests for Phase 4A reporting."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biolab_copilot.contracts import ArtifactFile, ReportManifest
from biolab_copilot.reporting.validation import load_json
from biolab_copilot.visualization.charts import render_generic_chart

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_report_manifest_round_trip_and_relative_artifact_contract() -> None:
    manifest = ReportManifest(
        report_id="report-test",
        report_type="generic_grouped",
        status="COMPLETED",
        source_manifests={"upstream": "a" * 64},
        source_artifacts={"source_file": "b" * 64},
        output_files=[
            ArtifactFile(
                path="report.docx",
                sha256="c" * 64,
                size_bytes=12,
                artifact_type="docx",
            )
        ],
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
    )

    restored = ReportManifest.model_validate_json(manifest.model_dump_json())

    assert restored == manifest
    assert "properties" in ReportManifest.model_json_schema()
    with pytest.raises(ValueError):
        ReportManifest.model_validate({**manifest.model_dump(), "absolute_path": "C:\\secret"})


def test_chart_bytes_are_deterministic_and_do_not_need_upstream_recalculation() -> None:
    raw_points = [
        {"group": "A", "measurement": 1.0},
        {"group": "A", "measurement": 2.0},
        {"group": "B", "measurement": 4.0},
        {"group": "B", "measurement": 5.0},
    ]
    group_statistics = [
        {"group": "A", "mean": 1.5, "sample_sd": 0.7071067811865476},
        {"group": "B", "mean": 4.5, "sample_sd": 0.7071067811865476},
    ]
    with TemporaryDirectory(dir=PROJECT_ROOT / "tests") as temporary:
        first = Path(temporary) / "first.png"
        second = Path(temporary) / "second.png"

        render_generic_chart(
            raw_points=raw_points,
            group_statistics=group_statistics,
            unit="AU",
            path=first,
        )
        render_generic_chart(
            raw_points=raw_points,
            group_statistics=group_statistics,
            unit="AU",
            path=second,
        )

        assert sha256(first.read_bytes()).hexdigest() == sha256(second.read_bytes()).hexdigest()


def test_report_json_loader_rejects_non_finite_values() -> None:
    with TemporaryDirectory(dir=PROJECT_ROOT / "tests") as temporary:
        path = Path(temporary) / "invalid.json"
        path.write_text(json.dumps({"value": float("nan")}), encoding="utf-8")

        with pytest.raises(ValueError, match="Non-finite"):
            load_json(path)
