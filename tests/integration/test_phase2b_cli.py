"""Offline CLI acceptance tests for the restricted Phase 2B workflow."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

import pytest

from biolab_copilot.contracts import IndependentTwoGroupDesign
from biolab_copilot.ingestion import read_source
from biolab_copilot.profiling import profile_and_validate

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with TemporaryDirectory(prefix="phase2b-cli-", dir=PROJECT_ROOT / "tests") as temp:
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


def _relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _make_artifact(
    case_dir: Path,
    rows: list[tuple[str, str, float, str, str, str]],
    *,
    experiment_type: str = "generic_grouped",
) -> Path:
    case_dir.mkdir(parents=True, exist_ok=True)
    source = case_dir / "source.csv"
    if experiment_type == "generic_grouped":
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
    else:
        source.write_text(
            "sample_id,sample_type,standard_concentration,measurement\n"
            "STD-1,standard,1,0.2\n",
            encoding="utf-8",
        )
        mapping = {
            "sample_id": "sample_id",
            "sample_type": "sample_type",
            "standard_concentration": "standard_concentration",
            "measurement": "measurement",
        }
    imported = profile_and_validate(
        read_source(source), experiment_type, mapping, parse_configuration={}
    )
    artifact = case_dir / "imported_data.json"
    artifact.write_text(imported.model_dump_json() + "\n", encoding="utf-8")
    return artifact


def _make_design(case_dir: Path, *, policy: Literal["none", "mean"] = "none") -> Path:
    case_dir.mkdir(parents=True, exist_ok=True)
    design = IndependentTwoGroupDesign(
        design_type="independent_two_group",
        experimental_unit_description="One explicitly identified independent experimental unit.",
        experimental_unit_id_field="experimental_unit_id",
        independence_declared=True,
        independence_rationale="The user declares that the groups contain independent units.",
        group_a="A",
        group_b="B",
        technical_repeat_policy=policy,
        method="welch_t",
        alternative="two-sided",
        alpha=0.05,
        confidence_level=0.95,
        assumptions_acknowledged=True,
    )
    path = case_dir / "design.json"
    path.write_text(design.model_dump_json() + "\n", encoding="utf-8")
    return path


def _confirm_plan(plan_path: Path) -> str:
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    payload["confirmed"] = True
    payload["warning_confirmations"] = {
        code: True for code in payload["required_confirmations"]
    }
    plan_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return hashlib.sha256(plan_path.read_bytes()).hexdigest()


def _normal_rows() -> list[tuple[str, str, float, str, str, str]]:
    return [
        ("A1", "A", 1, "U-A1", "biological", ""),
        ("A2", "A", 2, "U-A2", "biological", ""),
        ("A3", "A", 3, "U-A3", "biological", ""),
        ("B1", "B", 4, "U-B1", "biological", ""),
        ("B2", "B", 5, "U-B2", "biological", ""),
        ("B3", "B", 6, "U-B3", "biological", ""),
    ]


def test_cli_generates_preview_confirms_and_executes_welch(tmp_path: Path) -> None:
    artifact = _make_artifact(tmp_path, _normal_rows())
    design = _make_design(tmp_path)
    artifact_hash_before = hashlib.sha256(artifact.read_bytes()).hexdigest()
    source_path = Path(json.loads(artifact.read_text(encoding="utf-8"))["input_file"]["path"])
    source_hash_before = hashlib.sha256(source_path.read_bytes()).hexdigest()

    generated = _run_cli(
        "generate-welch-plan",
        _relative(artifact),
        "--design-file",
        _relative(design),
        "--output-dir",
        _relative(tmp_path / "plans"),
    )
    assert generated.returncode == 0, generated.stderr
    generated_payload = json.loads(generated.stdout)
    assert generated_payload["confirmed"] is False
    assert generated_payload["preview_ready"] is True
    plan_path = Path(generated_payload["plan_path"])
    preview_path = Path(generated_payload["preview_path"])
    assert json.loads(preview_path.read_text(encoding="utf-8"))["preview_ready"] is True

    unconfirmed = _run_cli(
        "execute-welch",
        _relative(plan_path),
        "--confirm-plan-sha256",
        generated_payload["plan_sha256"],
        "--output-dir",
        _relative(tmp_path / "unconfirmed"),
    )
    assert unconfirmed.returncode == 2
    unconfirmed_run = Path(json.loads(unconfirmed.stdout)["run_dir"])
    unconfirmed_result = json.loads(
        (unconfirmed_run / "analysis_result.json").read_text(encoding="utf-8")
    )
    assert unconfirmed_result["status"] == "failed"
    assert any(issue["code"] == "PLAN_NOT_CONFIRMED" for issue in unconfirmed_result["issues"])

    plan_hash = _confirm_plan(plan_path)
    executed = _run_cli(
        "execute-welch",
        _relative(plan_path),
        "--confirm-plan-sha256",
        plan_hash,
        "--output-dir",
        _relative(tmp_path / "runs"),
    )
    assert executed.returncode == 0, executed.stderr
    run_dir = Path(json.loads(executed.stdout)["run_dir"])
    result = json.loads((run_dir / "analysis_result.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "computed"
    assert result["analysis_level"] == "experimental_units"
    assert result["mean_difference"] == pytest.approx(-3)
    assert result["degrees_of_freedom"] == pytest.approx(4)
    assert result["independence_status"] == "user_declared_not_verified"
    assert result["independent_biological_n"] is None
    assert manifest["analysis_plan_sha256"] == plan_hash
    assert manifest["preview_sha256"] == generated_payload["preview_sha256"]
    assert manifest["input_artifact_sha256"] == artifact_hash_before
    assert manifest["software_versions"]["scipy"]
    assert {path.name for path in run_dir.iterdir()} == {
        "analysis_plan.json",
        "experimental_units.json",
        "analysis_result.json",
        "analysis_issues.json",
        "run_manifest.json",
    }
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == artifact_hash_before
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash_before
    result_text = (run_dir / "analysis_result.json").read_text(encoding="utf-8")
    assert "NaN" not in result_text
    assert "Infinity" not in result_text


def test_cli_rejects_changed_preview_and_wrong_plan_hash(tmp_path: Path) -> None:
    artifact = _make_artifact(tmp_path, _normal_rows())
    design = _make_design(tmp_path)
    generated = _run_cli(
        "welch-plan",
        _relative(artifact),
        "--design-file",
        _relative(design),
        "--output-dir",
        _relative(tmp_path / "plans"),
    )
    payload = json.loads(generated.stdout)
    plan_path = Path(payload["plan_path"])
    _confirm_plan(plan_path)
    wrong_hash = _run_cli(
        "execute-inferential",
        _relative(plan_path),
        "--confirm-plan-sha256",
        "0" * 64,
        "--output-dir",
        _relative(tmp_path / "wrong-hash"),
    )
    assert wrong_hash.returncode == 2
    assert "PLAN_HASH_MISMATCH" in wrong_hash.stderr

    preview_path = Path(payload["preview_path"])
    preview_path.write_text(preview_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed_plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    changed = _run_cli(
        "execute-welch",
        _relative(plan_path),
        "--confirm-plan-sha256",
        changed_plan_hash,
        "--output-dir",
        _relative(tmp_path / "changed-preview"),
    )
    assert changed.returncode == 2
    assert "PREVIEW_HASH_MISMATCH" in changed.stderr


def test_cli_blocks_duplicate_records_and_non_generic_inputs(tmp_path: Path) -> None:
    duplicate_rows = _normal_rows() + [("A1", "A", 1, "U-A1", "biological", "")]
    duplicate_artifact = _make_artifact(tmp_path / "duplicate", duplicate_rows)
    duplicate_design = _make_design(tmp_path / "duplicate")
    generated = _run_cli(
        "generate-welch-plan",
        _relative(duplicate_artifact),
        "--design-file",
        _relative(duplicate_design),
        "--output-dir",
        _relative(tmp_path / "duplicate" / "plans"),
    )
    assert generated.returncode == 2
    payload = json.loads(generated.stdout)
    plan_path = Path(payload["plan_path"])
    plan_hash = _confirm_plan(plan_path)
    blocked = _run_cli(
        "execute-welch",
        _relative(plan_path),
        "--confirm-plan-sha256",
        plan_hash,
        "--output-dir",
        _relative(tmp_path / "duplicate" / "runs"),
    )
    assert blocked.returncode == 2
    assert "DUPLICATE_COMPLETE_RECORD_INFERENTIAL" in blocked.stderr
    blocked_payload = json.loads(blocked.stdout)
    blocked_manifest = json.loads(
        (Path(blocked_payload["run_dir"]) / "run_manifest.json").read_text(encoding="utf-8")
    )
    assert blocked_manifest["analysis_ready"] is False

    elisa_dir = tmp_path / "elisa"
    elisa_artifact = _make_artifact(elisa_dir, [], experiment_type="elisa_standard_curve")
    elisa_design = _make_design(elisa_dir)
    rejected = _run_cli(
        "generate-welch-plan",
        _relative(elisa_artifact),
        "--design-file",
        _relative(elisa_design),
        "--output-dir",
        _relative(elisa_dir / "plans"),
    )
    assert rejected.returncode == 2
    assert "UNSUPPORTED_INPUT_ASSAY" in rejected.stderr


def test_cli_phase2a_plan_and_qc_error_cannot_enter_phase2b(tmp_path: Path) -> None:
    artifact = _make_artifact(tmp_path, _normal_rows())
    phase2a = _run_cli(
        "generate-plan",
        _relative(artifact),
        "--output-dir",
        _relative(tmp_path / "phase2a-plans"),
    )
    assert phase2a.returncode == 0
    phase2a_plan = Path(json.loads(phase2a.stdout)["plan_path"])
    blocked = _run_cli(
        "execute-welch",
        _relative(phase2a_plan),
        "--confirm-plan-sha256",
        hashlib.sha256(phase2a_plan.read_bytes()).hexdigest(),
        "--output-dir",
        _relative(tmp_path / "phase2a-as-phase2b"),
    )
    assert blocked.returncode == 2
    assert "UNSUPPORTED_PHASE2B_PLAN_LEVEL" in blocked.stderr

    bad_dir = tmp_path / "qc-error"
    bad_artifact = _make_artifact(
        bad_dir,
        [
            ("A1", "A", "not-a-number", "U-A1", "biological", ""),
            ("A2", "A", 2, "U-A2", "biological", ""),
            ("B1", "B", 4, "U-B1", "biological", ""),
            ("B2", "B", 5, "U-B2", "biological", ""),
        ],
    )
    bad_design = _make_design(bad_dir)
    bad_generated = _run_cli(
        "generate-welch-plan",
        _relative(bad_artifact),
        "--design-file",
        _relative(bad_design),
        "--output-dir",
        _relative(bad_dir / "plans"),
    )
    assert bad_generated.returncode == 2
    bad_plan = Path(json.loads(bad_generated.stdout)["plan_path"])
    bad_hash = _confirm_plan(bad_plan)
    bad_execution = _run_cli(
        "execute-welch",
        _relative(bad_plan),
        "--confirm-plan-sha256",
        bad_hash,
        "--output-dir",
        _relative(bad_dir / "runs"),
    )
    assert bad_execution.returncode == 2
    assert "IMPORT_QC_NOT_READY" in bad_execution.stderr
