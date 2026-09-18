"""Offline CLI acceptance tests for Phase 3A standard-only 4PL fitting."""

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

from biolab_copilot.contracts import ELISA4PLDesign

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="phase3a-cli-", dir=PROJECT_ROOT / "tests") as temp:
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


def _rows() -> list[tuple[str, str, str, str, str, str, str]]:
    concentrations = ["0", "0.1", "0.3", "1", "3", "10", "30", "100", "300"]
    values = [
        0.1,
        0.1198019801980198,
        0.158252427184466,
        0.2818181818181818,
        0.5615384615384615,
        1.1,
        1.6,
        1.918181818181818,
        2.035483870967742,
    ]
    return [
        (f"STD-{index}", "standard", concentration, repr(value), "ng/mL", "AU", f"R{index}")
        for index, (concentration, value) in enumerate(zip(concentrations, values, strict=True))
    ] + [("SAMPLE-1", "sample", "", "0.75", "ng/mL", "AU", "SAMPLE-R1")]


def _prepare_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source.csv"
    source.write_text(
        "sample_id,sample_type,standard_concentration,measurement,concentration_unit,measurement_unit,replicate_id\n"
        + "\n".join(",".join(row) for row in _rows())
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
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping) + "\n", encoding="utf-8")
    design = ELISA4PLDesign(
        curve_context_declared=True,
        curve_context_description="Synthetic CLI standard context.",
        concentration_unit="ng/mL",
        response_unit="AU",
        direction="increasing",
        standard_replicate_policy="none",
    )
    design_path = tmp_path / "design.json"
    design_path.write_text(design.model_dump_json() + "\n", encoding="utf-8")
    return source, mapping_path, design_path


def _confirm(plan_path: Path) -> str:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["confirmed"] = True
    payload["warning_confirmations"] = {
        code: True for code in payload["required_confirmations"]
    }
    plan_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(plan_path.read_bytes()).hexdigest()


def test_cli_import_plan_confirm_execute_and_exclude_unknown_sample(tmp_path: Path) -> None:
    source, mapping, design = _prepare_files(tmp_path)
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
    imported_dir = Path(json.loads(imported.stdout)["run_dir"])
    artifact = imported_dir / "imported_data.json"
    generated = _run_cli(
        "generate-4pl-plan",
        str(artifact.relative_to(PROJECT_ROOT)),
        "--design-file",
        str(design.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "plans").relative_to(PROJECT_ROOT)),
    )
    assert generated.returncode == 0, generated.stderr
    payload = json.loads(generated.stdout)
    plan_path = Path(payload["plan_path"])
    unconfirmed = _run_cli(
        "execute-4pl",
        str(plan_path.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        payload["plan_sha256"],
        "--output-dir",
        str((tmp_path / "unconfirmed").relative_to(PROJECT_ROOT)),
    )
    assert unconfirmed.returncode == 2
    plan_hash = _confirm(plan_path)
    executed = _run_cli(
        "execute-4pl",
        str(plan_path.relative_to(PROJECT_ROOT)),
        "--confirm-plan-sha256",
        plan_hash,
        "--output-dir",
        str((tmp_path / "runs").relative_to(PROJECT_ROOT)),
    )
    assert executed.returncode == 0, executed.stderr
    run_dir = Path(json.loads(executed.stdout)["run_dir"])
    result = json.loads((run_dir / "curve_fit_result.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "computed"
    assert result["n_fit_levels"] == 9
    assert result["curve_validated"] is False
    assert result["quantification_enabled"] is False
    assert result["source_record_references"]["excluded_records"] == [10]
    assert manifest["method"] == "four_parameter_logistic"
    assert manifest["analysis_plan_sha256"] == plan_hash
    assert manifest["standards_preview_sha256"] == payload["preview_sha256"]
    assert {path.name for path in run_dir.iterdir()} == {
        "analysis_plan.json",
        "standards_preview.json",
        "curve_fit_result.json",
        "analysis_issues.json",
        "run_manifest.json",
    }


def test_cli_constant_response_is_rejected_with_diagnostic(tmp_path: Path) -> None:
    source, mapping, design = _prepare_files(tmp_path)
    constant_source = tmp_path / "constant.csv"
    constant_lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        fields = line.split(",")
        if fields[0] != "sample_id":
            fields[3] = "1.0"
        constant_lines.append(",".join(fields))
    constant_source.write_text("\n".join(constant_lines) + "\n", encoding="utf-8")
    imported = _run_cli(
        "import",
        str(constant_source.relative_to(PROJECT_ROOT)),
        "--experiment-type",
        "elisa_standard_curve",
        "--mapping-file",
        str(mapping.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "constant-import").relative_to(PROJECT_ROOT)),
    )
    assert imported.returncode == 0
    artifact = Path(json.loads(imported.stdout)["run_dir"]) / "imported_data.json"
    generated = _run_cli(
        "generate-4pl-plan",
        str(artifact.relative_to(PROJECT_ROOT)),
        "--design-file",
        str(design.relative_to(PROJECT_ROOT)),
        "--output-dir",
        str((tmp_path / "constant-plans").relative_to(PROJECT_ROOT)),
    )
    assert generated.returncode == 2
    payload = json.loads(generated.stdout)
    preview = json.loads(Path(payload["preview_path"]).read_text(encoding="utf-8"))
    assert preview["preview_ready"] is False
    assert any(
        issue["code"] == "CONSTANT_STANDARD_RESPONSE"
        for issue in preview["blocking_reasons"]
    )
