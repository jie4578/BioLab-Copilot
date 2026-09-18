"""Offline CLI acceptance tests for Phase 1."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

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


def test_cli_import_success_writes_traceable_run_outputs() -> None:
    with TemporaryDirectory(prefix="phase1-cli-", dir=PROJECT_ROOT / "tests") as temp:
        result = _run_cli(
            "import",
            "examples/generic_grouped_normal.csv",
            "--experiment-type",
            "generic_grouped",
            "--mapping",
            '{"sample_id":"sample_id","group":"group","measurement":"measurement","replicate":"replicate_id"}',
            "--output-dir",
            temp,
        )

        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        run_dir = Path(summary["run_dir"])
        assert summary["analysis_ready"] is True
        assert {path.name for path in run_dir.iterdir()} == {
            "dataset_profile.json",
            "validation_issues.json",
            "imported_data.json",
            "run_manifest.json",
        }
        manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest["input_files"][0]["sha256"]
        assert manifest["analysis_ready"] is True
        assert manifest["assay_type"] == "generic_grouped"


def test_cli_error_exit_writes_diagnostics_and_marks_not_ready() -> None:
    with TemporaryDirectory(prefix="phase1-cli-", dir=PROJECT_ROOT / "tests") as temp:
        source = Path(temp) / "bad.csv"
        source.write_text(
            "sample_id,group,measurement\nS1,control,not-a-number\n",
            encoding="utf-8",
        )
        output_root = Path(temp) / "outputs"
        result = _run_cli(
            "import",
            str(source.relative_to(PROJECT_ROOT)),
            "--experiment-type",
            "generic_grouped",
            "--mapping",
            '{"sample_id":"sample_id","group":"group","measurement":"measurement"}',
            "--output-dir",
            str(output_root.relative_to(PROJECT_ROOT)),
        )

        assert result.returncode == 2
        summary = json.loads(result.stdout)
        run_dir = Path(summary["run_dir"])
        profile = json.loads((run_dir / "dataset_profile.json").read_text(encoding="utf-8"))
        issues = json.loads((run_dir / "validation_issues.json").read_text(encoding="utf-8"))
        assert profile["analysis_ready"] is False
        assert any(issue["code"] == "INVALID_NUMERIC" for issue in issues)


def test_cli_lists_xlsx_sheets_without_selecting_one() -> None:
    with TemporaryDirectory(prefix="phase1-cli-", dir=PROJECT_ROOT / "tests") as temp:
        source = Path(temp) / "sheets.xlsx"
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.title = "Data"
        workbook.create_sheet("Other")
        workbook.save(source)
        result = _run_cli("list-sheets", str(source.relative_to(PROJECT_ROOT)))

        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["sheets"] == ["Data", "Other"]


def test_phase1_source_has_no_network_or_provider_imports() -> None:
    forbidden_import = re.compile(
        r"^\s*(?:from|import)\s+(?:requests|httpx|urllib\.request|openai|langchain|gradio)\b",
        re.MULTILINE,
    )
    source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (PROJECT_ROOT / "src").rglob("*.py")
    )
    assert forbidden_import.search(source_text) is None
