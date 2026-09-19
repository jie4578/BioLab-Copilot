"""Offline CLI acceptance tests for research-only Phase 3B inverse estimation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from biolab_copilot.contracts import ELISA4PLDesign, ELISAInverseDesign

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="phase3b-cli-", dir=PROJECT_ROOT / "tests") as temp:
        yield Path(temp)


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "biolab_copilot.cli", *arguments],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def _response(x: float, direction: str = "increasing") -> float:
    return 0.1 + (2.0 * x / (10.0 + x) if direction == "increasing" else 2.0 * 10.0 / (10.0 + x))


def _prepare_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    concentrations = [1, 3, 10, 30, 100, 300, 1000, 3000]
    # Eight positive levels are required by Phase 3A's engineering guard.
    lines = [
        "sample_id,sample_type,standard_concentration,measurement,concentration_unit,measurement_unit,replicate_id,dilution_factor"
    ]
    for index, concentration in enumerate(sorted(concentrations)):
        lines.append(
            f"STD-{index},standard,{concentration},{_response(concentration)},ng/mL,AU,R{index},"
        )
    for index, concentration in enumerate([1.0, 10.0, 100.0, 0.1, 10000.0, 3.0]):
        lines.append(f"SAMPLE-{index},sample,,{_response(concentration)},ng/mL,AU,S{index},")
    source = tmp_path / "source.csv"
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    mapping = {
        "sample_id": "sample_id",
        "sample_type": "sample_type",
        "standard_concentration": "standard_concentration",
        "measurement": "measurement",
        "concentration_unit": "concentration_unit",
        "measurement_unit": "measurement_unit",
        "replicate_id": "replicate_id",
        "dilution_factor": "dilution_factor",
    }
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping) + "\n", encoding="utf-8")
    curve_design = ELISA4PLDesign(
        curve_context_declared=True,
        curve_context_description="Synthetic single-curve context.",
        concentration_unit="ng/mL",
        response_unit="AU",
        direction="increasing",
        standard_replicate_policy="none",
    )
    curve_design_path = tmp_path / "curve_design.json"
    curve_design_path.write_text(curve_design.model_dump_json() + "\n", encoding="utf-8")
    return source, mapping_path, curve_design_path


def _confirm(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["confirmed"] = True
    payload["warning_confirmations"] = {code: True for code in payload["required_confirmations"]}
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_cli_curve_then_inverse_preserves_rows_and_applies_dilution(tmp_path: Path) -> None:
    source, mapping, curve_design = _prepare_files(tmp_path)
    imported = _run_cli(
        "import",
        str(source.relative_to(PROJECT_ROOT)),
        "--experiment-type",
        "elisa_standard_curve",
        "--mapping-file",
        str(mapping.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "imported").relative_to(PROJECT_ROOT)),
    )
    assert imported.returncode == 0, imported.stderr
    import_dir = Path(json.loads(imported.stdout)["run_dir"])
    artifact = import_dir / "imported_data.json"
    generated_curve = _run_cli(
        "generate-4pl-plan",
        str(artifact.relative_to(PROJECT_ROOT)),
        "--design-file",
        str(curve_design.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "curve-plans").relative_to(PROJECT_ROOT)),
    )
    assert generated_curve.returncode == 0, generated_curve.stderr
    curve_plan = Path(json.loads(generated_curve.stdout)["plan_path"])
    curve_hash = _confirm(curve_plan)
    executed_curve = _run_cli(
        "execute-4pl",
        str(curve_plan.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        curve_hash,
        "--output-dir",
        str((tmp_path / "curve-runs").relative_to(PROJECT_ROOT)),
    )
    assert executed_curve.returncode == 0, executed_curve.stderr
    curve_run = Path(json.loads(executed_curve.stdout)["run_dir"])
    curve_result = curve_run / "curve_fit_result.json"

    inverse_design = ELISAInverseDesign(
        research_only_acknowledged=True,
        curve_context_compatibility_declared=True,
        curve_context_compatibility_rationale=(
            "The synthetic sample rows explicitly use the same response scale and curve context."
        ),
        sample_source_mode="same_import_artifact",
        dilution_factor_source="uniform_declared",
        uniform_dilution_factor=10.0,
    )
    inverse_design_path = tmp_path / "inverse_design.json"
    inverse_design_path.write_text(inverse_design.model_dump_json() + "\n", encoding="utf-8")
    generated_inverse = _run_cli(
        "generate-elisa-inverse-plan",
        str(curve_result.relative_to(PROJECT_ROOT)),
        "--design-file",
        str(inverse_design_path.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "inverse-plans").relative_to(PROJECT_ROOT)),
    )
    assert generated_inverse.returncode == 0, generated_inverse.stderr
    inverse_payload = json.loads(generated_inverse.stdout)
    inverse_plan = Path(inverse_payload["plan_path"])
    assert inverse_payload["confirmed"] is False
    changed_plan = json.loads(inverse_plan.read_text(encoding="utf-8"))
    changed_plan["uniform_dilution_factor"] = 2.0
    inverse_plan.write_text(json.dumps(changed_plan) + "\n", encoding="utf-8")
    stale_confirmation = _run_cli(
        "execute-elisa-inverse",
        str(inverse_plan.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        inverse_payload["plan_sha256"],
        "--output-dir",
        str((tmp_path / "inverse-stale").relative_to(PROJECT_ROOT)),
    )
    assert stale_confirmation.returncode == 2
    changed_plan["uniform_dilution_factor"] = 10.0
    inverse_plan.write_text(json.dumps(changed_plan) + "\n", encoding="utf-8")
    not_confirmed = _run_cli(
        "execute-elisa-inverse",
        str(inverse_plan.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        inverse_payload["plan_sha256"],
        "--output-dir",
        str((tmp_path / "inverse-unconfirmed").relative_to(PROJECT_ROOT)),
    )
    assert not_confirmed.returncode == 2
    inverse_hash = _confirm(inverse_plan)
    executed_inverse = _run_cli(
        "execute-elisa-inverse",
        str(inverse_plan.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        inverse_hash,
        "--output-dir",
        str((tmp_path / "inverse-runs").relative_to(PROJECT_ROOT)),
    )
    assert executed_inverse.returncode == 0, executed_inverse.stderr
    inverse_run = Path(json.loads(executed_inverse.stdout)["run_dir"])
    result = json.loads((inverse_run / "sample_concentrations.json").read_text(encoding="utf-8"))
    manifest = json.loads((inverse_run / "run_manifest.json").read_text(encoding="utf-8"))
    assert result["analysis_level"] == "measurement_rows"
    assert result["intended_use"] == "research_only"
    assert result["curve_validated"] is False
    assert result["validated_quantification_enabled"] is False
    assert result["successful_estimates"] == 4
    assert result["below_standard_span_count"] == 1
    assert result["above_standard_span_count"] == 1
    assert result["status"] == "partial"
    by_id = {item["sample_id"]: item for item in result["records"]}
    assert by_id["SAMPLE-0"]["concentration_in_assayed_sample"] == 1.0
    assert by_id["SAMPLE-0"]["concentration_in_original_sample"] == 10.0
    assert by_id["SAMPLE-3"]["concentration_in_assayed_sample"] is None
    assert by_id["SAMPLE-3"]["concentration_in_original_sample"] is None
    assert manifest["method"] == "four_parameter_logistic_inverse"
    assert manifest["analysis_plan_sha256"] == inverse_hash
    assert manifest["research_estimation_enabled"] is True
    assert {path.name for path in inverse_run.iterdir()} == {
        "analysis_plan.json",
        "sample_concentrations.json",
        "analysis_issues.json",
        "run_manifest.json",
    }


def test_cli_decreasing_curve_inverse_classifies_concentration_direction(tmp_path: Path) -> None:
    source = PROJECT_ROOT / "examples" / "phase3a_decreasing.csv"
    mapping = PROJECT_ROOT / "examples" / "phase3a_mapping.json"
    curve_design = PROJECT_ROOT / "examples" / "phase3a_design_decreasing.json"
    imported = _run_cli(
        "import",
        str(source.relative_to(PROJECT_ROOT)),
        "--experiment-type",
        "elisa_standard_curve",
        "--mapping-file",
        str(mapping.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "imported").relative_to(PROJECT_ROOT)),
    )
    assert imported.returncode == 0, imported.stderr
    artifact = Path(json.loads(imported.stdout)["run_dir"]) / "imported_data.json"
    generated_curve = _run_cli(
        "generate-4pl-plan",
        str(artifact.relative_to(PROJECT_ROOT)),
        "--design-file",
        str(curve_design.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "curve-plans").relative_to(PROJECT_ROOT)),
    )
    assert generated_curve.returncode == 0, generated_curve.stderr
    curve_payload = json.loads(generated_curve.stdout)
    curve_plan = Path(curve_payload["plan_path"])
    curve_hash = _confirm(curve_plan)
    executed_curve = _run_cli(
        "execute-4pl",
        str(curve_plan.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        curve_hash,
        "--output-dir",
        str((tmp_path / "curve-runs").relative_to(PROJECT_ROOT)),
    )
    assert executed_curve.returncode == 0, executed_curve.stderr
    curve_result = Path(json.loads(executed_curve.stdout)["run_dir"]) / "curve_fit_result.json"
    inverse_design = PROJECT_ROOT / "examples" / "phase3b_inverse_design.json"
    generated_inverse = _run_cli(
        "generate-elisa-inverse-plan",
        str(curve_result.relative_to(PROJECT_ROOT)),
        "--design-file",
        str(inverse_design.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "inverse-plans").relative_to(PROJECT_ROOT)),
    )
    assert generated_inverse.returncode == 0, generated_inverse.stderr
    inverse_payload = json.loads(generated_inverse.stdout)
    inverse_plan = Path(inverse_payload["plan_path"])
    inverse_hash = _confirm(inverse_plan)
    executed_inverse = _run_cli(
        "execute-elisa-inverse",
        str(inverse_plan.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        inverse_hash,
        "--output-dir",
        str((tmp_path / "inverse-runs").relative_to(PROJECT_ROOT)),
    )
    assert executed_inverse.returncode == 0, executed_inverse.stderr
    inverse_run = Path(json.loads(executed_inverse.stdout)["run_dir"])
    result = json.loads((inverse_run / "sample_concentrations.json").read_text(encoding="utf-8"))
    assert result["direction"] == "decreasing"
    assert result["successful_estimates"] == 1
    assert result["records"][0]["status"] == "estimated_within_standard_span"
    assert result["records"][0]["concentration_in_assayed_sample"] == pytest.approx(
        20.0 / 0.65 - 10.0, rel=1e-10
    )
