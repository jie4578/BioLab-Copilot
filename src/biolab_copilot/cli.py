"""Offline command-line interface for Phase 1 import and structural QC."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openpyxl

from biolab_copilot import __version__
from biolab_copilot.assays import suggest_column_mapping
from biolab_copilot.contracts import (
    ArtifactFile,
    DatasetProfile,
    ImportResult,
    InputFile,
    IssueSeverity,
    RunManifest,
    RunStatus,
    ValidationIssue,
)
from biolab_copilot.ingestion import (
    InputReadError,
    ReaderLimits,
    list_xlsx_sheets,
    read_source,
    sha256_file,
)
from biolab_copilot.profiling import profile_and_validate

EXIT_OK = 0
EXIT_QC_ERRORS = 2
EXIT_FATAL = 3


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _path_inside_project(path: str | Path) -> Path:
    candidate = Path(path).resolve()
    root = _project_root()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path must remain inside the project directory: {candidate}") from exc
    return candidate


def _parse_mapping(value: str | None, mapping_file: str | None) -> dict[str, str]:
    if value is not None:
        raw = json.loads(value)
    elif mapping_file is not None:
        raw = json.loads(_path_inside_project(mapping_file).read_text(encoding="utf-8"))
    else:
        raise ValueError("An explicit --mapping or --mapping-file is required.")
    if not isinstance(raw, dict) or not all(
        isinstance(source, str) and isinstance(target, str) for source, target in raw.items()
    ):
        raise ValueError(
            "Column mapping must be a JSON object of source_column to canonical_field strings."
        )
    return dict(raw)


def _limits_from_args(args: argparse.Namespace) -> ReaderLimits:
    return ReaderLimits(
        max_file_bytes=args.max_file_bytes,
        max_rows=args.max_rows,
        max_uncompressed_bytes=args.max_uncompressed_bytes,
        max_zip_members=args.max_zip_members,
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _issue_payload(issues: list[ValidationIssue]) -> list[dict[str, Any]]:
    return [issue.model_dump(mode="json") for issue in issues]


def _run_directory(output_root: Path) -> tuple[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        run_id = f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        run_dir = output_root / run_id
        try:
            run_dir.mkdir()
            return run_id, run_dir
        except FileExistsError:
            continue
    raise RuntimeError("Could not create a unique output run directory.")


def _output_file(path: Path, artifact_type: str) -> ArtifactFile:
    return ArtifactFile(
        path=str(path.resolve()),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        artifact_type=artifact_type,
    )


def _write_success_outputs(
    result: ImportResult,
    *,
    run_id: str,
    run_dir: Path,
    started_at: datetime,
    finished_at: datetime,
    configuration: dict[str, Any],
) -> list[ArtifactFile]:
    profile_path = run_dir / "dataset_profile.json"
    issues_path = run_dir / "validation_issues.json"
    records_path = run_dir / "imported_data.json"
    _write_json(profile_path, result.dataset_profile.model_dump(mode="json"))
    _write_json(issues_path, _issue_payload(result.validation_issues))
    _write_json(records_path, result.model_dump(mode="json"))
    artifacts = [
        _output_file(profile_path, "dataset_profile"),
        _output_file(issues_path, "validation_issues"),
        _output_file(records_path, "imported_data"),
    ]
    manifest = RunManifest(
        run_id=run_id,
        experiment_id=run_id,
        status=RunStatus.COMPLETED if result.analysis_ready else RunStatus.PARTIAL,
        input_files=[result.input_file],
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "openpyxl": openpyxl.__version__,
        },
        warnings=[
            issue for issue in result.validation_issues if issue.severity == IssueSeverity.WARNING
        ],
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        assay_type=result.experiment_type,
        column_mapping=result.column_mapping,
        parse_configuration=result.parse_configuration,
        output_files=artifacts,
        analysis_ready=result.analysis_ready,
    )
    manifest_path = run_dir / "run_manifest.json"
    _write_json(manifest_path, manifest.model_dump(mode="json"))
    return artifacts + [_output_file(manifest_path, "run_manifest")]


def _empty_profile(input_file: InputFile, issue_count: dict[IssueSeverity, int]) -> DatasetProfile:
    return DatasetProfile(
        dataset_id=Path(input_file.path).stem,
        source_filename=Path(input_file.path).name,
        source_sha256=input_file.sha256,
        row_count=0,
        column_count=0,
        column_names=[],
        missing_value_count=0,
        analysis_ready=False,
        parsed_record_count=0,
        error_record_count=0,
        warning_count=issue_count[IssueSeverity.WARNING],
        error_count=issue_count[IssueSeverity.ERROR],
        blocking_count=issue_count[IssueSeverity.BLOCKING],
    )


def _write_failure_outputs(
    *,
    issues: list[ValidationIssue],
    input_file: InputFile | None,
    run_id: str,
    run_dir: Path,
    started_at: datetime,
    finished_at: datetime,
    configuration: dict[str, Any],
) -> None:
    issues_path = run_dir / "validation_issues.json"
    records_path = run_dir / "imported_data.json"
    _write_json(issues_path, _issue_payload(issues))
    _write_json(records_path, {"schema_version": "1.0", "records": []})
    issue_count = {
        severity: sum(1 for issue in issues if issue.severity == severity)
        for severity in IssueSeverity
    }
    artifacts: list[ArtifactFile] = [
        _output_file(issues_path, "validation_issues"),
        _output_file(records_path, "imported_data"),
    ]
    if input_file is not None:
        profile_path = run_dir / "dataset_profile.json"
        profile = _empty_profile(input_file, issue_count)
        _write_json(profile_path, profile.model_dump(mode="json"))
        artifacts.insert(0, _output_file(profile_path, "dataset_profile"))
    manifest = RunManifest(
        run_id=run_id,
        experiment_id=run_id,
        status=RunStatus.FAILED,
        input_files=[input_file] if input_file is not None else [],
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "openpyxl": openpyxl.__version__,
        },
        warnings=[issue for issue in issues if issue.severity == IssueSeverity.WARNING],
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        output_files=artifacts,
        analysis_ready=False,
    )
    _write_json(run_dir / "run_manifest.json", manifest.model_dump(mode="json"))


def _print_issues(issues: list[ValidationIssue]) -> None:
    for issue in issues:
        print(f"{issue.severity.value}: {issue.code}: {issue.message}", file=sys.stderr)


def _add_common_reader_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-file-bytes", type=int, default=50_000_000)
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument("--max-uncompressed-bytes", type=int, default=500_000_000)
    parser.add_argument("--max-zip-members", type=int, default=10_000)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="biolab-copilot", description="Offline BioLab Copilot Phase 1 tools"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-sheets", help="List .xlsx worksheet names")
    list_parser.add_argument("input")
    _add_common_reader_options(list_parser)

    suggest_parser = subparsers.add_parser(
        "suggest-mapping", help="Suggest, but do not apply, header mappings"
    )
    suggest_parser.add_argument("input")
    suggest_parser.add_argument(
        "--experiment-type", required=True, choices=["generic_grouped", "elisa_standard_curve"]
    )
    suggest_parser.add_argument("--sheet")
    suggest_parser.add_argument("--encoding", default="utf-8-sig")
    suggest_parser.add_argument("--delimiter", default=",")
    _add_common_reader_options(suggest_parser)

    import_parser = subparsers.add_parser(
        "import", help="Import and structurally QC one CSV/XLSX source"
    )
    import_parser.add_argument("input")
    import_parser.add_argument(
        "--experiment-type", required=True, choices=["generic_grouped", "elisa_standard_curve"]
    )
    mapping_group = import_parser.add_mutually_exclusive_group(required=True)
    mapping_group.add_argument(
        "--mapping", help="Explicit JSON object: source_column to canonical_field"
    )
    mapping_group.add_argument(
        "--mapping-file", help="Project-local JSON file containing the explicit mapping"
    )
    import_parser.add_argument("--sheet")
    import_parser.add_argument("--encoding", default="utf-8-sig")
    import_parser.add_argument("--delimiter", default=",")
    import_parser.add_argument("--output-dir", default="runs")
    _add_common_reader_options(import_parser)
    return parser


def _run_list_sheets(args: argparse.Namespace) -> int:
    try:
        input_path = _path_inside_project(args.input)
        sheets = list_xlsx_sheets(input_path, limits=_limits_from_args(args))
        payload = {"path": str(input_path), "sha256": sha256_file(input_path), "sheets": sheets}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK
    except (InputReadError, OSError, ValueError) as exc:
        if isinstance(exc, InputReadError):
            _print_issues(exc.issues)
        else:
            print(str(exc), file=sys.stderr)
        return EXIT_QC_ERRORS


def _run_suggest_mapping(args: argparse.Namespace) -> int:
    try:
        input_path = _path_inside_project(args.input)
        table = read_source(
            input_path,
            sheet_name=args.sheet,
            encoding=args.encoding,
            delimiter=args.delimiter,
            limits=_limits_from_args(args),
        )
        _print_issues(list(table.issues))
        print(
            json.dumps(
                suggest_column_mapping(list(table.headers), args.experiment_type),
                ensure_ascii=False,
                indent=2,
            )
        )
        return (
            EXIT_QC_ERRORS
            if any(
                issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
                for issue in table.issues
            )
            else EXIT_OK
        )
    except (InputReadError, OSError, ValueError) as exc:
        if isinstance(exc, InputReadError):
            _print_issues(exc.issues)
        else:
            print(str(exc), file=sys.stderr)
        return EXIT_QC_ERRORS


def _run_import(args: argparse.Namespace) -> int:
    started_at = datetime.now(UTC)
    run_id = "uncreated"
    run_dir: Path | None = None
    try:
        input_path = _path_inside_project(args.input)
        output_root = _path_inside_project(args.output_dir)
        if output_root == input_path.parent:
            raise ValueError("Output directory must be separate from the input file directory.")
        mapping = _parse_mapping(args.mapping, args.mapping_file)
        run_id, run_dir = _run_directory(output_root)
        configuration = {
            "input_path": str(input_path),
            "experiment_type": args.experiment_type,
            "sheet": args.sheet,
            "encoding": args.encoding,
            "delimiter": args.delimiter,
            "limits": vars(_limits_from_args(args)),
        }
        table = read_source(
            input_path,
            sheet_name=args.sheet,
            encoding=args.encoding,
            delimiter=args.delimiter,
            limits=_limits_from_args(args),
        )
        result = profile_and_validate(
            table,
            args.experiment_type,
            mapping,
            parse_configuration=configuration,
        )
        finished_at = datetime.now(UTC)
        _write_success_outputs(
            result,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            configuration=configuration,
        )
        _print_issues(result.validation_issues)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir),
                    "analysis_ready": result.analysis_ready,
                },
                indent=2,
            )
        )
        return (
            EXIT_OK
            if result.analysis_ready
            or not any(
                issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
                for issue in result.validation_issues
            )
            else EXIT_QC_ERRORS
        )
    except (InputReadError, OSError, ValueError, json.JSONDecodeError) as exc:
        finished_at = datetime.now(UTC)
        issues = (
            exc.issues
            if isinstance(exc, InputReadError)
            else [
                ValidationIssue(
                    code="CLI_INPUT_ERROR",
                    severity=IssueSeverity.BLOCKING,
                    message=str(exc),
                    location="cli",
                    suggested_action=(
                        "Correct the command arguments and rerun without changing "
                        "the original source."
                    ),
                )
            ]
        )
        _print_issues(issues)
        if run_dir is not None:
            _write_failure_outputs(
                issues=issues,
                input_file=exc.input_file if isinstance(exc, InputReadError) else None,
                run_id=run_id,
                run_dir=run_dir,
                started_at=started_at,
                finished_at=finished_at,
                configuration={"command": "import", "input": args.input},
            )
        return EXIT_QC_ERRORS
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"fatal: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FATAL


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "list-sheets":
        return _run_list_sheets(args)
    if args.command == "suggest-mapping":
        return _run_suggest_mapping(args)
    if args.command == "import":
        return _run_import(args)
    return EXIT_FATAL


if __name__ == "__main__":
    raise SystemExit(main())
