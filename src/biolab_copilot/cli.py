"""Offline command-line interface for import, QC, and confirmed statistics."""

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
import pydantic
import scipy

from biolab_copilot import __version__
from biolab_copilot.assays import suggest_column_mapping
from biolab_copilot.contracts import (
    AnalysisPlan,
    AnalysisResult,
    ArtifactFile,
    CurveFitResult,
    DatasetProfile,
    ExperimentalUnitsPreview,
    ImportResult,
    InputFile,
    IssueSeverity,
    RunManifest,
    RunStatus,
    SampleConcentrationsResult,
    StandardsPreview,
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
from biolab_copilot.reporting import (
    ReportRenderError,
    render_elisa_report,
    render_generic_report,
    render_welch_report,
)
from biolab_copilot.statistics import (
    build_4pl_plan,
    build_analysis_plan,
    build_inverse_plan,
    build_welch_plan,
    compute_4pl_fit,
    compute_grouped_descriptive,
    compute_inverse_result,
    compute_welch_result,
    validate_4pl_execution_inputs,
    validate_execution_inputs,
    validate_inverse_execution_inputs,
    validate_welch_execution_inputs,
)

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
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
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
        prog="biolab-copilot", description="Offline BioLab Copilot import and statistics tools"
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

    plan_parser = subparsers.add_parser(
        "generate-plan",
        aliases=["plan"],
        help="Generate an unconfirmed generic_grouped Phase 2A analysis plan",
    )
    plan_parser.add_argument("input_artifact")
    plan_parser.add_argument("--output-dir", default="outputs/phase2a-plans")

    execute_parser = subparsers.add_parser(
        "execute-plan",
        aliases=["execute"],
        help="Execute a confirmed generic_grouped Phase 2A analysis plan",
    )
    execute_parser.add_argument("plan_file")
    execute_parser.add_argument("--confirm-plan-sha256", required=True)
    execute_parser.add_argument("--output-dir", default="outputs/phase2a")

    welch_plan_parser = subparsers.add_parser(
        "generate-welch-plan",
        aliases=["welch-plan"],
        help="Generate an unconfirmed Phase 2B two-group Welch plan and unit preview",
    )
    welch_plan_parser.add_argument("input_artifact")
    welch_plan_parser.add_argument("--design-file", required=True)
    welch_plan_parser.add_argument("--output-dir", default="outputs/phase2b-plans")

    welch_execute_parser = subparsers.add_parser(
        "execute-welch",
        aliases=["execute-inferential"],
        help="Execute a confirmed Phase 2B two-group Welch plan",
    )
    welch_execute_parser.add_argument("plan_file")
    welch_execute_parser.add_argument("--confirm-plan-sha256", required=True)
    welch_execute_parser.add_argument("--output-dir", default="outputs/phase2b")

    curve_plan_parser = subparsers.add_parser(
        "generate-4pl-plan",
        aliases=["4pl-plan"],
        help="Generate an unconfirmed ELISA standard-only 4PL plan and preview",
    )
    curve_plan_parser.add_argument("input_artifact")
    curve_plan_parser.add_argument("--design-file", required=True)
    curve_plan_parser.add_argument("--output-dir", default="outputs/phase3a-plans")

    curve_execute_parser = subparsers.add_parser(
        "execute-4pl",
        aliases=["execute-curve-fit"],
        help="Execute a confirmed ELISA standard-only 4PL plan",
    )
    curve_execute_parser.add_argument("plan_file")
    curve_execute_parser.add_argument("--confirm-plan-sha256", required=True)
    curve_execute_parser.add_argument("--output-dir", default="outputs/phase3a")

    inverse_plan_parser = subparsers.add_parser(
        "generate-elisa-inverse-plan",
        aliases=["elisa-inverse-plan"],
        help="Generate an unconfirmed research-only ELISA 4PL inverse plan and preview",
    )
    inverse_plan_parser.add_argument("curve_result")
    inverse_plan_parser.add_argument("--design-file", required=True)
    inverse_plan_parser.add_argument("--output-dir", default="outputs/phase3b-plans")

    inverse_execute_parser = subparsers.add_parser(
        "execute-elisa-inverse",
        aliases=["elisa-inverse"],
        help="Execute a confirmed research-only ELISA 4PL inverse plan",
    )
    inverse_execute_parser.add_argument("plan_file")
    inverse_execute_parser.add_argument("--confirm-plan-sha256", required=True)
    inverse_execute_parser.add_argument("--output-dir", default="outputs/phase3b")

    generic_report_parser = subparsers.add_parser(
        "render-generic-report",
        help="Render a deterministic generic descriptive report from one Phase 2A run",
    )
    generic_report_parser.add_argument("--analysis-dir", required=True)
    generic_report_parser.add_argument("--output-dir", required=True)

    welch_report_parser = subparsers.add_parser(
        "render-welch-report",
        help="Render a deterministic Welch report from one Phase 2B run",
    )
    welch_report_parser.add_argument("--analysis-dir", required=True)
    welch_report_parser.add_argument("--output-dir", required=True)

    elisa_report_parser = subparsers.add_parser(
        "render-elisa-report",
        help="Render a deterministic ELISA 4PL report from explicit Phase 3A/3B runs",
    )
    elisa_report_parser.add_argument("--curve-dir", required=True)
    elisa_report_parser.add_argument("--inverse-dir")
    elisa_report_parser.add_argument("--output-dir", required=True)
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


def _phase2a_issue(code: str, message: str, suggested_action: str) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=IssueSeverity.BLOCKING,
        message=message,
        location="cli",
        suggested_action=suggested_action,
    )


def _load_import_artifact_for_plan(path: Path) -> ImportResult:
    return ImportResult.model_validate_json(path.read_text(encoding="utf-8"))


def _run_generate_plan(args: argparse.Namespace) -> int:
    try:
        input_path = _path_inside_project(args.input_artifact)
        output_root = _path_inside_project(args.output_dir)
        if output_root == input_path.parent:
            raise ValueError(
                "Plan output directory must be separate from the input artifact directory."
            )
        import_result = _load_import_artifact_for_plan(input_path)
        if import_result.experiment_type != "generic_grouped":
            raise ValueError("Phase 2A plan generation supports only generic_grouped.")
        plan = build_analysis_plan(input_path, import_result)
        run_id, run_dir = _run_directory(output_root)
        plan_path = run_dir / "analysis_plan.json"
        _write_json(plan_path, plan.model_dump(mode="json"))
        plan_hash = sha256_file(plan_path)
        print(
            json.dumps(
                {
                    "plan_id": plan.plan_id,
                    "plan_path": str(plan_path.resolve()),
                    "plan_sha256": plan_hash,
                    "confirmed": plan.confirmed,
                    "required_confirmations": plan.required_confirmations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return EXIT_OK
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "PLAN_GENERATION_FAILED",
            str(exc),
            (
                "Use an unchanged generic_grouped imported_data.json artifact and a separate "
                "output directory."
            ),
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _phase2a_failed_result(
    plan: AnalysisPlan,
    plan_sha256: str,
    issues: list[ValidationIssue],
    import_result: ImportResult | None,
) -> AnalysisResult:
    return AnalysisResult(
        result_id=f"result-{uuid.uuid4().hex[:12]}",
        experiment_id=plan.experiment_id,
        plan_id=plan.plan_id,
        status="failed",
        issues=issues,
        analysis_level="measurement_rows",
        declared_units=plan.declared_units,
        independent_biological_n=None,
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=(
            import_result.input_file.sha256 if import_result is not None else plan.source_sha256
        ),
        confirmed_plan_sha256=plan_sha256,
        statistical_limitations=[
            "No successful statistics were produced because execution preflight failed.",
            "independent_biological_n is not determined in Phase 2A and remains null.",
        ],
    )


def _write_phase2a_outputs(
    *,
    plan_bytes: bytes,
    plan: AnalysisPlan,
    result: AnalysisResult,
    issues: list[ValidationIssue],
    plan_sha256: str,
    run_id: str,
    run_dir: Path,
    started_at: datetime,
    finished_at: datetime,
    configuration: dict[str, Any],
    import_result: ImportResult | None,
) -> None:
    plan_path = run_dir / "analysis_plan.json"
    plan_path.write_bytes(plan_bytes)
    result_path = run_dir / "analysis_result.json"
    issues_path = run_dir / "analysis_issues.json"
    _write_json(result_path, result.model_dump(mode="json"))
    _write_json(issues_path, _issue_payload(issues))
    artifacts = [
        _output_file(plan_path, "analysis_plan"),
        _output_file(result_path, "analysis_result"),
        _output_file(issues_path, "analysis_issues"),
    ]
    manifest = RunManifest(
        run_id=run_id,
        experiment_id=plan.experiment_id,
        status=RunStatus.COMPLETED if result.status == "computed" else RunStatus.FAILED,
        input_files=[import_result.input_file] if import_result is not None else [],
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "pydantic": pydantic.__version__,
            "statistics_implementation": "phase2a-descriptive-v1",
        },
        warnings=[issue for issue in issues if issue.severity == IssueSeverity.WARNING],
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        assay_type=plan.assay_type,
        column_mapping=plan.column_mapping,
        parse_configuration=plan.configuration,
        output_files=artifacts,
        analysis_ready=result.status == "computed",
        analysis_level="measurement_rows",
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=(
            import_result.input_file.sha256 if import_result is not None else plan.source_sha256
        ),
        analysis_plan_sha256=plan_sha256,
    )
    _write_json(run_dir / "run_manifest.json", manifest.model_dump(mode="json"))


def _run_execute_plan(args: argparse.Namespace) -> int:
    started_at = datetime.now(UTC)
    try:
        plan_path = _path_inside_project(args.plan_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root == plan_path.parent:
            raise ValueError("Analysis output directory must be separate from the plan directory.")
        run_id, run_dir = _run_directory(output_root)
        plan_bytes = plan_path.read_bytes()
        preflight = validate_execution_inputs(
            plan_path,
            args.confirm_plan_sha256,
            allowed_root=_project_root(),
        )
        plan = preflight.plan
        import_result = preflight.import_result
        all_issues = [
            *(import_result.validation_issues if import_result is not None else []),
            *preflight.issues,
        ]
        if preflight.issues:
            result = _phase2a_failed_result(plan, preflight.plan_sha256, all_issues, import_result)
        elif import_result is None:  # pragma: no cover - guarded by preflight issues
            result = _phase2a_failed_result(
                plan,
                preflight.plan_sha256,
                [
                    _phase2a_issue(
                        "INPUT_ARTIFACT_INVALID",
                        "No validated import artifact is available for execution.",
                        "Regenerate the plan from an unchanged Phase 1 import artifact.",
                    )
                ],
                None,
            )
            all_issues = result.issues
        else:
            result = compute_grouped_descriptive(
                import_result,
                plan,
                preflight.plan_sha256,
            )
            all_issues = result.issues
        finished_at = datetime.now(UTC)
        _write_phase2a_outputs(
            plan_bytes=plan_bytes,
            plan=plan,
            result=result,
            issues=all_issues,
            plan_sha256=preflight.plan_sha256,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            configuration={
                "command": "execute-plan",
                "plan_path": str(plan_path),
                "confirmed_plan_sha256": args.confirm_plan_sha256,
            },
            import_result=import_result,
        )
        _print_issues(all_issues)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir.resolve()),
                    "status": result.status,
                    "analysis_ready": result.status == "computed",
                    "plan_sha256": preflight.plan_sha256,
                },
                indent=2,
            )
        )
        return EXIT_OK if result.status == "computed" else EXIT_QC_ERRORS
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "EXECUTION_FAILED",
            str(exc),
            (
                "Verify the plan path, explicit plan hash, and separate project-local output "
                "directory."
            ),
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _run_generate_welch_plan(args: argparse.Namespace) -> int:
    """Generate a Phase 2B plan and a deterministic experimental-unit preview."""

    try:
        input_path = _path_inside_project(args.input_artifact)
        design_path = _path_inside_project(args.design_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root in {input_path.parent, design_path.parent}:
            raise ValueError(
                "Phase 2B plan output must be separate from the input artifact and design file."
            )
        run_id, run_dir = _run_directory(output_root)
        preview_path = run_dir / "experimental_units.json"
        build = build_welch_plan(input_path, design_path, preview_path)
        _write_json(preview_path, build.preview.model_dump(mode="json"))
        preview_sha256 = sha256_file(preview_path)
        plan = build.plan.model_copy(update={"preview_sha256": preview_sha256})
        plan_path = run_dir / "analysis_plan.json"
        _write_json(plan_path, plan.model_dump(mode="json"))
        plan_sha256 = sha256_file(plan_path)
        _print_issues(list(build.issues))
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "plan_id": plan.plan_id,
                    "plan_path": str(plan_path.resolve()),
                    "plan_sha256": plan_sha256,
                    "preview_path": str(preview_path.resolve()),
                    "preview_sha256": preview_sha256,
                    "preview_ready": build.preview.preview_ready,
                    "confirmed": plan.confirmed,
                    "required_confirmations": plan.required_confirmations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return (
            EXIT_OK
            if not any(
                issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
                for issue in build.issues
            )
            else EXIT_QC_ERRORS
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "WELCH_PLAN_GENERATION_FAILED",
            str(exc),
            (
                "Use a project-local Phase 1 import artifact, explicit design file, "
                "and separate output directory."
            ),
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _write_phase2b_outputs(
    *,
    plan_bytes: bytes,
    plan: AnalysisPlan,
    preview: ExperimentalUnitsPreview | None,
    result: AnalysisResult,
    issues: list[ValidationIssue],
    plan_sha256: str,
    run_id: str,
    run_dir: Path,
    started_at: datetime,
    finished_at: datetime,
    configuration: dict[str, Any],
    import_result: ImportResult | None,
) -> None:
    plan_path = run_dir / "analysis_plan.json"
    plan_path.write_bytes(plan_bytes)
    preview_path = run_dir / "experimental_units.json"
    if preview is not None:
        _write_json(preview_path, preview.model_dump(mode="json"))
    else:
        _write_json(
            preview_path,
            {
                "schema_version": "1.0",
                "preview_ready": False,
                "blocking_reasons": _issue_payload(issues),
            },
        )
    result_path = run_dir / "analysis_result.json"
    issues_path = run_dir / "analysis_issues.json"
    _write_json(result_path, result.model_dump(mode="json"))
    _write_json(issues_path, _issue_payload(issues))
    artifacts = [
        _output_file(plan_path, "analysis_plan"),
        _output_file(preview_path, "experimental_units"),
        _output_file(result_path, "analysis_result"),
        _output_file(issues_path, "analysis_issues"),
    ]
    manifest = RunManifest(
        run_id=run_id,
        experiment_id=plan.experiment_id,
        status=RunStatus.COMPLETED if result.status == "computed" else RunStatus.FAILED,
        input_files=[import_result.input_file] if import_result is not None else [],
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "pydantic": pydantic.__version__,
            "scipy": scipy.__version__,
            "statistics_implementation": "phase2b-welch-v1",
        },
        warnings=[issue for issue in issues if issue.severity == IssueSeverity.WARNING],
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        assay_type=plan.assay_type,
        column_mapping=plan.column_mapping,
        parse_configuration=plan.configuration,
        output_files=artifacts,
        analysis_ready=result.status == "computed",
        analysis_level="experimental_units",
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=(
            import_result.input_file.sha256 if import_result is not None else plan.source_sha256
        ),
        analysis_plan_sha256=plan_sha256,
        preview_sha256=plan.preview_sha256,
        method=plan.method,
        independence_status=result.independence_status,
    )
    _write_json(run_dir / "run_manifest.json", manifest.model_dump(mode="json"))


def _run_execute_welch(args: argparse.Namespace) -> int:
    """Execute only a fully confirmed and revalidated Phase 2B plan."""

    started_at = datetime.now(UTC)
    try:
        plan_path = _path_inside_project(args.plan_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root == plan_path.parent:
            raise ValueError("Phase 2B output must be separate from the plan directory.")
        run_id, run_dir = _run_directory(output_root)
        plan_bytes = plan_path.read_bytes()
        preflight = validate_welch_execution_inputs(
            plan_path,
            args.confirm_plan_sha256,
            allowed_root=_project_root(),
        )
        result = compute_welch_result(preflight)
        import_result = preflight.import_result
        issues = [
            *(import_result.validation_issues if import_result is not None else []),
            *preflight.issues,
        ]
        if result.status == "computed":
            issues = result.issues
        finished_at = datetime.now(UTC)
        _write_phase2b_outputs(
            plan_bytes=plan_bytes,
            plan=preflight.plan,
            preview=preflight.preview,
            result=result,
            issues=issues,
            plan_sha256=preflight.plan_sha256,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            configuration={
                "command": "execute-welch",
                "plan_path": str(plan_path),
                "confirmed_plan_sha256": args.confirm_plan_sha256,
            },
            import_result=import_result,
        )
        _print_issues(issues)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir.resolve()),
                    "status": result.status,
                    "analysis_ready": result.status == "computed",
                    "plan_sha256": preflight.plan_sha256,
                },
                indent=2,
            )
        )
        return EXIT_OK if result.status == "computed" else EXIT_QC_ERRORS
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "WELCH_EXECUTION_FAILED",
            str(exc),
            (
                "Verify the plan path, explicit plan hash, and separate project-local "
                "output directory."
            ),
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _write_phase3a_outputs(
    *,
    plan_bytes: bytes,
    plan: AnalysisPlan,
    preview: StandardsPreview | None,
    result: CurveFitResult,
    issues: list[ValidationIssue],
    plan_sha256: str,
    run_id: str,
    run_dir: Path,
    started_at: datetime,
    finished_at: datetime,
    configuration: dict[str, Any],
    import_result: ImportResult | None,
) -> None:
    plan_path = run_dir / "analysis_plan.json"
    plan_path.write_bytes(plan_bytes)
    preview_path = run_dir / "standards_preview.json"
    if preview is not None:
        _write_json(preview_path, preview.model_dump(mode="json"))
    else:
        _write_json(
            preview_path,
            {
                "schema_version": "1.0",
                "preview_ready": False,
                "blocking_reasons": _issue_payload(issues),
            },
        )
    result_path = run_dir / "curve_fit_result.json"
    issues_path = run_dir / "analysis_issues.json"
    _write_json(result_path, result.model_dump(mode="json"))
    _write_json(issues_path, _issue_payload(issues))
    artifacts = [
        _output_file(plan_path, "analysis_plan"),
        _output_file(preview_path, "standards_preview"),
        _output_file(result_path, "curve_fit_result"),
        _output_file(issues_path, "analysis_issues"),
    ]
    manifest = RunManifest(
        run_id=run_id,
        experiment_id=plan.experiment_id,
        status=RunStatus.COMPLETED if result.status == "computed" else RunStatus.FAILED,
        input_files=[import_result.input_file] if import_result is not None else [],
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "pydantic": pydantic.__version__,
            "scipy": scipy.__version__,
            "statistics_implementation": "phase3a-4pl-standard-only-v1",
        },
        warnings=[issue for issue in issues if issue.severity == IssueSeverity.WARNING],
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        assay_type=plan.assay_type,
        column_mapping=plan.column_mapping,
        parse_configuration=plan.configuration,
        output_files=artifacts,
        analysis_ready=result.status == "computed",
        analysis_level="standard_curve_levels",
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=(
            import_result.input_file.sha256 if import_result is not None else plan.source_sha256
        ),
        analysis_plan_sha256=plan_sha256,
        preview_sha256=plan.standards_preview_sha256,
        method="four_parameter_logistic",
        curve_validated=False,
        quantification_enabled=False,
        standards_preview_sha256=plan.standards_preview_sha256,
    )
    _write_json(run_dir / "run_manifest.json", manifest.model_dump(mode="json"))


def _run_generate_4pl_plan(args: argparse.Namespace) -> int:
    """Generate an explicit, unconfirmed Phase 3A standard-only plan."""

    try:
        input_path = _path_inside_project(args.input_artifact)
        design_path = _path_inside_project(args.design_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root in {input_path.parent, design_path.parent}:
            raise ValueError(
                "Phase 3A plan output must be separate from the input artifact and design file."
            )
        run_id, run_dir = _run_directory(output_root)
        preview_path = run_dir / "standards_preview.json"
        build = build_4pl_plan(input_path, design_path, preview_path)
        _write_json(preview_path, build.preview.model_dump(mode="json"))
        preview_sha256 = sha256_file(preview_path)
        plan = build.plan.model_copy(update={"standards_preview_sha256": preview_sha256})
        plan_path = run_dir / "analysis_plan.json"
        _write_json(plan_path, plan.model_dump(mode="json"))
        plan_sha256 = sha256_file(plan_path)
        _print_issues(list(build.issues))
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "plan_id": plan.plan_id,
                    "plan_path": str(plan_path.resolve()),
                    "plan_sha256": plan_sha256,
                    "preview_path": str(preview_path.resolve()),
                    "preview_sha256": preview_sha256,
                    "preview_ready": build.preview.preview_ready,
                    "confirmed": plan.confirmed,
                    "required_confirmations": plan.required_confirmations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return (
            EXIT_OK
            if not any(
                issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
                for issue in build.issues
            )
            else EXIT_QC_ERRORS
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "FOUR_PL_PLAN_GENERATION_FAILED",
            str(exc),
            (
                "Use a project-local ELISA import artifact, explicit 4PL design file, "
                "and separate output directory."
            ),
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _run_execute_4pl(args: argparse.Namespace) -> int:
    """Execute only a confirmed, fully revalidated Phase 3A plan."""

    started_at = datetime.now(UTC)
    try:
        plan_path = _path_inside_project(args.plan_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root == plan_path.parent:
            raise ValueError("Phase 3A output must be separate from the plan directory.")
        run_id, run_dir = _run_directory(output_root)
        plan_bytes = plan_path.read_bytes()
        preflight = validate_4pl_execution_inputs(
            plan_path,
            args.confirm_plan_sha256,
            allowed_root=_project_root(),
        )
        result = compute_4pl_fit(preflight)
        import_result = preflight.import_result
        issues = result.issues
        finished_at = datetime.now(UTC)
        _write_phase3a_outputs(
            plan_bytes=plan_bytes,
            plan=preflight.plan,
            preview=preflight.preview,
            result=result,
            issues=issues,
            plan_sha256=preflight.plan_sha256,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            configuration={
                "command": "execute-4pl",
                "plan_path": str(plan_path),
                "confirmed_plan_sha256": args.confirm_plan_sha256,
            },
            import_result=import_result,
        )
        _print_issues(issues)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir.resolve()),
                    "status": result.status,
                    "analysis_ready": result.status == "computed",
                    "plan_sha256": preflight.plan_sha256,
                },
                indent=2,
            )
        )
        return EXIT_OK if result.status == "computed" else EXIT_QC_ERRORS
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "FOUR_PL_EXECUTION_FAILED",
            str(exc),
            (
                "Verify the plan path, explicit plan hash, and separate project-local "
                "output directory."
            ),
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _write_phase3b_outputs(
    *,
    plan_bytes: bytes,
    plan: AnalysisPlan,
    result: SampleConcentrationsResult,
    issues: list[ValidationIssue],
    plan_sha256: str,
    run_id: str,
    run_dir: Path,
    started_at: datetime,
    finished_at: datetime,
    configuration: dict[str, Any],
    preflight: Any,
) -> None:
    """Write an independent Phase 3B run without modifying curve artifacts."""
    plan_path = run_dir / "analysis_plan.json"
    plan_path.write_bytes(plan_bytes)
    result_path = run_dir / "sample_concentrations.json"
    issues_path = run_dir / "analysis_issues.json"
    _write_json(result_path, result.model_dump(mode="json"))
    _write_json(issues_path, _issue_payload(issues))
    artifacts = [
        _output_file(plan_path, "analysis_plan"),
        _output_file(result_path, "sample_concentrations"),
        _output_file(issues_path, "analysis_issues"),
    ]
    sample_import = preflight.sample_import
    manifest = RunManifest(
        run_id=run_id,
        experiment_id=plan.experiment_id,
        status=(
            RunStatus.COMPLETED
            if result.status == "computed"
            else RunStatus.PARTIAL
            if result.status == "partial"
            else RunStatus.FAILED
        ),
        input_files=[sample_import.input_file] if sample_import is not None else [],
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "pydantic": pydantic.__version__,
            "scipy": scipy.__version__,
            "statistics_implementation": "phase3b-4pl-inverse-v1",
        },
        warnings=[issue for issue in issues if issue.severity == IssueSeverity.WARNING],
        created_at=started_at,
        started_at=started_at,
        finished_at=finished_at,
        assay_type="elisa_standard_curve",
        column_mapping=plan.column_mapping,
        parse_configuration=plan.configuration,
        output_files=artifacts,
        analysis_ready=result.status == "computed",
        analysis_level="measurement_rows",
        input_artifact_sha256=plan.inverse_sample_artifact_sha256,
        source_sha256=plan.inverse_sample_source_sha256,
        analysis_plan_sha256=plan_sha256,
        method="four_parameter_logistic_inverse",
        curve_validated=False,
        quantification_enabled=False,
        intended_use="research_only",
        research_only_acknowledged=True,
        validated_quantification_enabled=False,
        research_estimation_enabled=True,
        curve_fit_result_sha256=plan.inverse_curve_fit_result_sha256,
        sample_artifact_sha256=plan.inverse_sample_artifact_sha256,
        sample_result_sha256=sha256_file(result_path),
    )
    _write_json(run_dir / "run_manifest.json", manifest.model_dump(mode="json"))


def _run_generate_elisa_inverse_plan(args: argparse.Namespace) -> int:
    """Generate a research-only inverse plan; generation never confirms it."""
    try:
        curve_result_path = _path_inside_project(args.curve_result)
        design_path = _path_inside_project(args.design_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root in {curve_result_path.parent, design_path.parent}:
            raise ValueError(
                "Phase 3B plan output must be separate from the curve run and design file."
            )
        run_id, run_dir = _run_directory(output_root)
        preview_path = run_dir / "sample_preview.json"
        build = build_inverse_plan(
            curve_result_path,
            design_path,
            preview_path,
            allowed_root=_project_root(),
        )
        _write_json(preview_path, build.preview.model_dump(mode="json"))
        preview_sha256 = sha256_file(preview_path)
        plan = build.plan.model_copy(update={"inverse_preview_sha256": preview_sha256})
        plan_path = run_dir / "analysis_plan.json"
        _write_json(plan_path, plan.model_dump(mode="json"))
        plan_sha256 = sha256_file(plan_path)
        _print_issues(list(build.issues))
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "plan_id": plan.plan_id,
                    "plan_path": str(plan_path.resolve()),
                    "plan_sha256": plan_sha256,
                    "preview_path": str(preview_path.resolve()),
                    "preview_sha256": preview_sha256,
                    "preview_ready": build.preview.preview_ready,
                    "confirmed": plan.confirmed,
                    "required_confirmations": plan.required_confirmations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return (
            EXIT_OK
            if not any(
                issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
                for issue in build.issues
            )
            else EXIT_QC_ERRORS
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "ELISA_INVERSE_PLAN_GENERATION_FAILED",
            str(exc),
            "Use project-local Phase 3A artifacts, an explicit inverse design, and "
            "a separate output directory.",
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _run_execute_elisa_inverse(args: argparse.Namespace) -> int:
    """Execute only a confirmed, fully revalidated research-only inverse plan."""
    started_at = datetime.now(UTC)
    try:
        plan_path = _path_inside_project(args.plan_file)
        output_root = _path_inside_project(args.output_dir)
        if output_root == plan_path.parent:
            raise ValueError("Phase 3B output must be separate from the plan directory.")
        run_id, run_dir = _run_directory(output_root)
        plan_bytes = plan_path.read_bytes()
        preflight = validate_inverse_execution_inputs(
            plan_path,
            args.confirm_plan_sha256,
            allowed_root=_project_root(),
        )
        result = compute_inverse_result(preflight)
        issues = [*preflight.issues, *result.issues]
        finished_at = datetime.now(UTC)
        _write_phase3b_outputs(
            plan_bytes=plan_bytes,
            plan=preflight.plan,
            result=result,
            issues=issues,
            plan_sha256=preflight.plan_sha256,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            configuration={
                "command": "execute-elisa-inverse",
                "plan_path": str(plan_path),
                "confirmed_plan_sha256": args.confirm_plan_sha256,
                "curve_fit_result_path": preflight.plan.inverse_curve_fit_result_path,
                "sample_artifact_path": preflight.plan.inverse_sample_artifact_path,
            },
            preflight=preflight,
        )
        _print_issues(issues)
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_dir": str(run_dir.resolve()),
                    "status": result.status,
                    "analysis_ready": result.status == "computed",
                    "plan_sha256": preflight.plan_sha256,
                    "successful_estimates": result.successful_estimates,
                    "total_sample_measurements": result.total_sample_measurements,
                },
                indent=2,
            )
        )
        has_error = any(
            issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING} for issue in issues
        )
        return (
            EXIT_OK
            if result.status in {"computed", "partial"} and not has_error
            else EXIT_QC_ERRORS
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issue = _phase2a_issue(
            "ELISA_INVERSE_EXECUTION_FAILED",
            str(exc),
            "Verify the plan path, explicit plan hash, and separate project-local "
            "output directory.",
        )
        _print_issues([issue])
        return EXIT_QC_ERRORS


def _run_render_generic_report(args: argparse.Namespace) -> int:
    try:
        manifest_path = render_generic_report(
            _path_inside_project(args.analysis_dir),
            _path_inside_project(args.output_dir),
        )
        print(
            json.dumps(
                {"report_manifest": str(manifest_path.resolve()), "status": "COMPLETED"},
                indent=2,
            )
        )
        return EXIT_OK
    except ReportRenderError as exc:
        print(f"blocking: REPORT_RENDER_FAILED: {exc}", file=sys.stderr)
        return EXIT_QC_ERRORS


def _run_render_welch_report(args: argparse.Namespace) -> int:
    try:
        manifest_path = render_welch_report(
            _path_inside_project(args.analysis_dir),
            _path_inside_project(args.output_dir),
        )
        print(
            json.dumps(
                {"report_manifest": str(manifest_path.resolve()), "status": "COMPLETED"},
                indent=2,
            )
        )
        return EXIT_OK
    except ReportRenderError as exc:
        print(f"blocking: REPORT_RENDER_FAILED: {exc}", file=sys.stderr)
        return EXIT_QC_ERRORS


def _run_render_elisa_report(args: argparse.Namespace) -> int:
    try:
        manifest_path = render_elisa_report(
            _path_inside_project(args.curve_dir),
            _path_inside_project(args.output_dir),
            _path_inside_project(args.inverse_dir) if args.inverse_dir else None,
        )
        print(
            json.dumps(
                {"report_manifest": str(manifest_path.resolve()), "status": "COMPLETED"},
                indent=2,
            )
        )
        return EXIT_OK
    except ReportRenderError as exc:
        print(f"blocking: REPORT_RENDER_FAILED: {exc}", file=sys.stderr)
        return EXIT_QC_ERRORS


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "list-sheets":
        return _run_list_sheets(args)
    if args.command == "suggest-mapping":
        return _run_suggest_mapping(args)
    if args.command == "import":
        return _run_import(args)
    if args.command in {"generate-plan", "plan"}:
        return _run_generate_plan(args)
    if args.command in {"execute-plan", "execute"}:
        return _run_execute_plan(args)
    if args.command in {"generate-welch-plan", "welch-plan"}:
        return _run_generate_welch_plan(args)
    if args.command in {"execute-welch", "execute-inferential"}:
        return _run_execute_welch(args)
    if args.command in {"generate-4pl-plan", "4pl-plan"}:
        return _run_generate_4pl_plan(args)
    if args.command in {"execute-4pl", "execute-curve-fit"}:
        return _run_execute_4pl(args)
    if args.command in {"generate-elisa-inverse-plan", "elisa-inverse-plan"}:
        return _run_generate_elisa_inverse_plan(args)
    if args.command in {"execute-elisa-inverse", "elisa-inverse"}:
        return _run_execute_elisa_inverse(args)
    if args.command == "render-generic-report":
        return _run_render_generic_report(args)
    if args.command == "render-welch-report":
        return _run_render_welch_report(args)
    if args.command == "render-elisa-report":
        return _run_render_elisa_report(args)
    return EXIT_FATAL


if __name__ == "__main__":
    raise SystemExit(main())
