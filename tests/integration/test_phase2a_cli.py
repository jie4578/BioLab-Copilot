"""Offline CLI acceptance tests for the Phase 2A plan and statistics workflow."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from biolab_copilot.ingestion import read_source
from biolab_copilot.profiling import profile_and_validate

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def _make_import_artifact(
    case_dir: Path,
    *,
    rows: str,
    experiment_type: str = "generic_grouped",
) -> Path:
    source = case_dir / "source.csv"
    if experiment_type == "generic_grouped":
        source.write_text(
            "sample_id,group,measurement,replicate_type\n" + rows,
            encoding="utf-8",
        )
        mapping = {
            "sample_id": "sample_id",
            "group": "group",
            "measurement": "measurement",
            "replicate_type": "replicate_type",
        }
    else:
        source.write_text(
            "sample_id,sample_type,standard_concentration,measurement\n" + rows,
            encoding="utf-8",
        )
        mapping = {
            "sample_id": "sample_id",
            "sample_type": "sample_type",
            "standard_concentration": "standard_concentration",
            "measurement": "measurement",
        }
    result = profile_and_validate(read_source(source), experiment_type, mapping)
    artifact = case_dir / f"{experiment_type}_imported_data.json"
    artifact.write_text(result.model_dump_json() + "\n", encoding="utf-8")
    return artifact


def _relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


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


def test_cli_requires_confirmation_then_executes_traceable_statistics() -> None:
    with TemporaryDirectory(prefix="phase2a-cli-", dir=PROJECT_ROOT / "tests") as temp:
        case_dir = Path(temp)
        artifact = _make_import_artifact(
            case_dir,
            rows="S1,control,1,biological\nS2,treatment,3,biological\n",
        )
        artifact_hash_before = hashlib.sha256(artifact.read_bytes()).hexdigest()
        source_path = Path(
            json.loads(artifact.read_text(encoding="utf-8"))["input_file"]["path"]
        )
        source_hash_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
        plans_dir = case_dir / "plans"
        generated = _run_cli(
            "generate-plan",
            _relative(artifact),
            "--output-dir",
            _relative(plans_dir),
        )

        assert generated.returncode == 0, generated.stderr
        generated_payload = json.loads(generated.stdout)
        plan_path = Path(generated_payload["plan_path"])
        assert generated_payload["confirmed"] is False

        unconfirmed = _run_cli(
            "execute-plan",
            _relative(plan_path),
            "--confirm-plan-sha256",
            generated_payload["plan_sha256"],
            "--output-dir",
            _relative(case_dir / "unconfirmed-runs"),
        )
        assert unconfirmed.returncode == 2
        unconfirmed_summary = json.loads(unconfirmed.stdout)
        unconfirmed_result = json.loads(
            (Path(unconfirmed_summary["run_dir"]) / "analysis_result.json").read_text(
                encoding="utf-8"
            )
        )
        assert unconfirmed_result["status"] == "failed"
        assert unconfirmed_result["analysis_level"] == "measurement_rows"
        assert any(issue["code"] == "PLAN_NOT_CONFIRMED" for issue in unconfirmed_result["issues"])

        plan_hash = _confirm_plan(plan_path)
        executed = _run_cli(
            "execute-plan",
            _relative(plan_path),
            "--confirm-plan-sha256",
            plan_hash,
            "--output-dir",
            _relative(case_dir / "runs"),
        )
        assert executed.returncode == 0, executed.stderr
        run_dir = Path(json.loads(executed.stdout)["run_dir"])
        result = json.loads((run_dir / "analysis_result.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        assert result["status"] == "computed"
        assert result["independent_biological_n"] is None
        assert result["confirmed_plan_sha256"] == plan_hash
        assert {item["group"] for item in result["group_statistics"]} == {
            "control",
            "treatment",
        }
        assert manifest["analysis_plan_sha256"] == plan_hash
        assert manifest["input_artifact_sha256"] == artifact_hash_before
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == artifact_hash_before
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash_before
        assert all("sha256" in item for item in manifest["output_files"])
        result_text = (run_dir / "analysis_result.json").read_text(encoding="utf-8")
        assert "NaN" not in result_text
        assert "Infinity" not in result_text


def test_cli_rejects_wrong_plan_hash_and_changed_input_artifact() -> None:
    with TemporaryDirectory(prefix="phase2a-binding-", dir=PROJECT_ROOT / "tests") as temp:
        case_dir = Path(temp)
        artifact = _make_import_artifact(
            case_dir,
            rows="S1,control,1,biological\nS2,control,2,biological\n",
        )
        generated = _run_cli(
            "plan",
            _relative(artifact),
            "--output-dir",
            _relative(case_dir / "plans"),
        )
        assert generated.returncode == 0
        plan_path = Path(json.loads(generated.stdout)["plan_path"])
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
        original_configuration = plan_payload["configuration"]
        wrong_hash = _run_cli(
            "execute",
            _relative(plan_path),
            "--confirm-plan-sha256",
            "0" * 64,
            "--output-dir",
            _relative(case_dir / "wrong-hash-runs"),
        )
        assert wrong_hash.returncode == 2
        assert "PLAN_HASH_MISMATCH" in wrong_hash.stderr

        plan_hash = _confirm_plan(plan_path)
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
        plan_payload["configuration"]["delimiter"] = ";"
        plan_path.write_text(
            json.dumps(plan_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        configuration_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        configuration_changed = _run_cli(
            "execute",
            _relative(plan_path),
            "--confirm-plan-sha256",
            configuration_hash,
            "--output-dir",
            _relative(case_dir / "changed-configuration-runs"),
        )
        assert configuration_changed.returncode == 2
        assert "PARSER_CONFIGURATION_BINDING_MISMATCH" in configuration_changed.stderr

        plan_payload["configuration"] = original_configuration
        plan_path.write_text(
            json.dumps(plan_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        artifact.write_text(artifact.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        changed = _run_cli(
            "execute",
            _relative(plan_path),
            "--confirm-plan-sha256",
            plan_hash,
            "--output-dir",
            _relative(case_dir / "changed-input-runs"),
        )
        assert changed.returncode == 2
        assert "INPUT_ARTIFACT_HASH_MISMATCH" in changed.stderr
        assert "analysis_ready" in changed.stdout


def test_cli_requires_duplicate_warning_confirmation_and_keeps_both_rows() -> None:
    with TemporaryDirectory(prefix="phase2a-duplicate-", dir=PROJECT_ROOT / "tests") as temp:
        case_dir = Path(temp)
        artifact = _make_import_artifact(
            case_dir,
            rows="S1,control,1,biological\nS1,control,1,biological\n",
        )
        generated = _run_cli(
            "generate-plan",
            _relative(artifact),
            "--output-dir",
            _relative(case_dir / "plans"),
        )
        assert generated.returncode == 0
        plan_path = Path(json.loads(generated.stdout)["plan_path"])
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
        assert "DUPLICATE_COMPLETE_RECORD" in payload["required_confirmations"]
        payload["confirmed"] = True
        plan_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        unconfirmed_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        blocked = _run_cli(
            "execute-plan",
            _relative(plan_path),
            "--confirm-plan-sha256",
            unconfirmed_hash,
            "--output-dir",
            _relative(case_dir / "blocked-runs"),
        )
        assert blocked.returncode == 2
        assert "REQUIRED_WARNING_NOT_CONFIRMED" in blocked.stderr

        payload["warning_confirmations"]["DUPLICATE_COMPLETE_RECORD"] = True
        payload["warning_confirmations"]["SINGLE_OBSERVATION_GROUP"] = True
        plan_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        confirmed_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        accepted = _run_cli(
            "execute-plan",
            _relative(plan_path),
            "--confirm-plan-sha256",
            confirmed_hash,
            "--output-dir",
            _relative(case_dir / "accepted-runs"),
        )
        assert accepted.returncode == 0, accepted.stderr
        run_dir = Path(json.loads(accepted.stdout)["run_dir"])
        result = json.loads((run_dir / "analysis_result.json").read_text(encoding="utf-8"))
        assert result["group_statistics"][0]["n_measurements"] == 2
        assert result["group_statistics"][0]["source_record_numbers"] == [1, 2]


def test_cli_rejects_elisa_plan_generation_and_qc_error_execution() -> None:
    with TemporaryDirectory(prefix="phase2a-boundaries-", dir=PROJECT_ROOT / "tests") as temp:
        case_dir = Path(temp)
        elisa = _make_import_artifact(
            case_dir,
            experiment_type="elisa_standard_curve",
            rows="STD-1,standard,1,0.2\n",
        )
        rejected = _run_cli(
            "generate-plan",
            _relative(elisa),
            "--output-dir",
            _relative(case_dir / "elisa-plans"),
        )
        assert rejected.returncode == 2
        assert "generic_grouped" in rejected.stderr

        qc_error = _make_import_artifact(
            case_dir,
            rows="S1,control,not-a-number,biological\n",
        )
        generated = _run_cli(
            "generate-plan",
            _relative(qc_error),
            "--output-dir",
            _relative(case_dir / "qc-plans"),
        )
        assert generated.returncode == 0
        plan_path = Path(json.loads(generated.stdout)["plan_path"])
        plan_hash = _confirm_plan(plan_path)
        blocked = _run_cli(
            "execute-plan",
            _relative(plan_path),
            "--confirm-plan-sha256",
            plan_hash,
            "--output-dir",
            _relative(case_dir / "qc-runs"),
        )
        assert blocked.returncode == 2
        assert "IMPORT_QC_NOT_READY" in blocked.stderr
