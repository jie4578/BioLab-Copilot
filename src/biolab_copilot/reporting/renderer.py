"""Deterministic DOCX, XLSX, JSON, and PNG report-package rendering."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

from biolab_copilot import __version__
from biolab_copilot.contracts import (
    AnalysisResult,
    CurveFitResult,
    ExperimentalUnitsPreview,
    ReportManifest,
    SampleConcentrationsResult,
    StandardsPreview,
)
from biolab_copilot.visualization.charts import (
    render_elisa_curve_chart,
    render_elisa_residual_chart,
    render_generic_chart,
    render_status_counts_chart,
    render_welch_chart,
)

from .validation import (
    AnalysisPackage,
    UpstreamValidationError,
    load_elisa_curve_package,
    load_elisa_inverse_package,
    load_generic_package,
    load_welch_package,
    sha256_file,
    validate_elisa_inverse_binding,
    warning_count,
)


class ReportRenderError(ValueError):
    """A user-facing report rendering or upstream-validation failure."""


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) > 500:
        text = text[:500]
    project_root = str(Path(__file__).resolve().parents[3])
    text = text.replace(project_root, "<project>")
    text = text.replace("C:\\Users\\Administrator", "<local-user>")
    text = text.replace("C:/Users/Administrator", "<local-user>")
    return text


def _safe_location(value: Any) -> str | None:
    return _safe_string(value)


def _model_payload(model: Any) -> dict[str, Any]:
    return dict(model.model_dump(mode="json"))


def _source_descriptor(package: AnalysisPackage) -> dict[str, Any]:
    return {
        "source_filename": Path(package.input_artifact.input_file.path).name,
        "source_sha256": package.input_artifact.input_file.sha256,
        "source_size_bytes": package.input_artifact.input_file.size_bytes,
        "input_artifact_sha256": package.plan.input_artifact_sha256,
        "upstream_run_id": package.manifest.run_id,
        "upstream_manifest_sha256": package.manifest_sha256,
    }


def _issue_payload(
    package: AnalysisPackage,
    extra: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    issues = list(package.issues)
    result_issues = getattr(package.result, "issues", [])
    issues.extend(_model_payload(item) for item in result_issues)
    issues.extend(_model_payload(item) for item in package.manifest.warnings)
    if extra:
        issues.extend(extra)
    return issues


def _artifact_roles(package: AnalysisPackage) -> dict[str, str]:
    roles = dict(package.artifact_hashes)
    roles["input_artifact"] = package.plan.input_artifact_sha256 or ""
    roles["source_file"] = package.input_artifact.input_file.sha256
    roles["upstream_manifest"] = package.manifest_sha256
    return roles


def _new_output_dir(output_dir: Path) -> Path:
    project_root = Path(__file__).resolve().parents[3]
    resolved = output_dir.resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise ReportRenderError("Report output must remain inside the project directory.") from exc
    if resolved.exists():
        raise ReportRenderError("Report output directory already exists; choose a new directory.")
    resolved.mkdir(parents=True)
    (resolved / "charts").mkdir()
    return resolved


def _report_id(report_type: str, sources: dict[str, str], configuration: dict[str, Any]) -> str:
    stable = json.dumps(
        {"report_type": report_type, "sources": sources, "configuration": configuration},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"report-{hashlib.sha256(stable).hexdigest()[:16]}"


def _common_data(
    *,
    report_type: str,
    package: AnalysisPackage,
    title: str,
    scope: str,
    methods: dict[str, Any],
    results: dict[str, Any],
    warnings: list[dict[str, Any]],
    charts: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    configuration = {"report_type": report_type, "source_order": "explicit_input_order"}
    sources = _artifact_roles(package)
    report_id = _report_id(report_type, sources, configuration)
    data = {
        "schema_version": "1.0",
        "report_version": "1.0",
        "report_id": report_id,
        "report_type": report_type,
        "title": title,
        "scope": scope,
        "source": _source_descriptor(package),
        "methods": methods,
        "qc": {"warning_counts": warning_count(warnings), "issues": warnings},
        "results": results,
        "charts": charts,
        "limitations": [
            (
                "This report renders completed structured artifacts and does not "
                "recalculate upstream scientific results."
            ),
            "Report generation success does not establish scientific validity or assay validation.",
        ],
    }
    return data, {"configuration": configuration, "sources": sources, "report_id": report_id}


def _generic_data(
    package: AnalysisPackage,
    chart_names: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = package.result
    assert isinstance(result, AnalysisResult)
    raw_points: list[dict[str, Any]] = []
    for record in package.input_artifact.records:
        group = record.parsed_values.get("group")
        measurement = record.parsed_values.get("measurement")
        if group is None or measurement is None:
            continue
        raw_points.append(
            {
                "record_number": record.record_number,
                "sample_id": _safe_string(record.parsed_values.get("sample_id")),
                "group": _safe_string(group),
                "measurement": measurement,
                "replicate_type": _safe_string(record.parsed_values.get("replicate_type")),
                "source_location": _safe_location(next(iter(record.source_locations.values()), "")),
            }
        )
    group_statistics = [_model_payload(item) for item in result.group_statistics]
    return _common_data(
        report_type="generic_grouped",
        package=package,
        title="Generic grouped descriptive analysis",
        scope="Measurement-row descriptive statistics only.",
        methods={
            "analysis_level": "measurement_rows",
            "statistics": result.statistics,
            "sample_sd_ddof": package.plan.sample_sd_ddof,
            "independent_biological_n": None,
            "repeat_policy": (
                "All source measurement rows are retained and described; no repeat "
                "aggregation is performed."
            ),
        },
        results={
            "group_statistics": group_statistics,
            "measurements": raw_points,
            "independent_biological_n": None,
            "source_record_references": result.source_record_references,
            "declared_units": result.declared_units,
        },
        warnings=_issue_payload(package),
        charts=chart_names,
    )


def _welch_data(
    package: AnalysisPackage,
    preview: ExperimentalUnitsPreview,
    chart_names: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = package.result
    assert isinstance(result, AnalysisResult)
    units = [_model_payload(item) for item in result.experimental_unit_summaries]
    source_rows = [_model_payload(item) for item in preview.rows]
    stats = [_model_payload(item) for item in result.inferential_group_statistics]
    comparison = {
        key: getattr(result, key)
        for key in (
            "mean_difference",
            "mean_difference_ci_lower",
            "mean_difference_ci_upper",
            "t_statistic",
            "degrees_of_freedom",
            "p_value",
            "alpha",
            "alternative",
            "method",
        )
    }
    return _common_data(
        report_type="welch_two_group",
        package=package,
        title="Welch two group comparison",
        scope="One confirmed two-sided Welch comparison at experimental-unit level.",
        methods={
            "analysis_level": "experimental_units",
            "experimental_unit_description": package.plan.experimental_unit_description,
            "independence_status": result.independence_status,
            "technical_repeat_policy": result.technical_repeat_policy,
            "assumptions_acknowledged": package.plan.assumptions_acknowledged,
        },
        results={
            "group_statistics": stats,
            "experimental_units": units,
            "technical_source_records": source_rows,
            "comparison": comparison,
            "source_record_references": result.source_record_references,
            "independent_biological_n": None,
        },
        warnings=_issue_payload(package),
        charts=chart_names,
    )


def _elisa_data(
    curve: AnalysisPackage,
    standards: StandardsPreview,
    inverse: AnalysisPackage | None,
    chart_names: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    curve_result = curve.result
    assert isinstance(curve_result, CurveFitResult)
    curve_payload = _model_payload(curve_result)
    standard_records = [_model_payload(item) for item in standards.records]
    fit_levels = [_model_payload(item) for item in standards.fit_levels]
    residuals = [
        {
            "concentration": item["concentration"],
            "observed": item["observed"],
            "predicted": item["predicted"],
            "residual": item["residual"],
            "source_record_numbers": item["source_record_numbers"],
        }
        for item in curve_payload["fit_points"]
    ]
    warnings = _issue_payload(curve)
    inverse_payload: dict[str, Any] | None = None
    if inverse is not None:
        inverse_result = inverse.result
        assert isinstance(inverse_result, SampleConcentrationsResult)
        inverse_payload = _model_payload(inverse_result)
        warnings.extend(_issue_payload(inverse))
    sources = _artifact_roles(curve)
    if inverse is not None:
        sources.update({f"inverse_{key}": value for key, value in _artifact_roles(inverse).items()})
    configuration = {
        "report_type": "elisa_4pl",
        "include_inverse": inverse is not None,
        "source_order": "explicit_input_order",
    }
    report_id = _report_id("elisa_4pl", sources, configuration)
    source = _source_descriptor(curve)
    if inverse is not None:
        source["inverse_source"] = _source_descriptor(inverse)
    data = {
        "schema_version": "1.0",
        "report_version": "1.0",
        "report_id": report_id,
        "report_type": "elisa_4pl",
        "title": "ELISA 4PL standard curve analysis",
        "scope": (
            "Standard-only 4PL diagnostics with optional research-only "
            "per-measurement estimates."
        ),
        "source": source,
        "methods": {
            "analysis_level": "standard_curve_levels",
            "model": "four_parameter_logistic",
            "direction": curve_result.direction,
            "concentration_unit": curve_result.concentration_unit,
            "response_unit": curve_result.response_unit,
            "standard_replicate_policy": standards.standard_replicate_policy,
            "curve_validated": False,
            "validated_quantification_enabled": False,
            "blank_policy": curve.plan.blank_policy,
            "weighting": curve.plan.weighting,
            "loss": curve.plan.loss,
        },
        "qc": {"warning_counts": warning_count(warnings), "issues": warnings},
        "results": {
            "curve_parameters": {
                key: curve_payload[key]
                for key in (
                    "lower_asymptote",
                    "upper_asymptote",
                    "midpoint_concentration",
                    "slope_magnitude",
                    "direction",
                    "concentration_unit",
                    "response_unit",
                )
            },
            "diagnostics": {
                key: curve_payload[key]
                for key in (
                    "n_fit_levels",
                    "n_raw_standard_measurements",
                    "observed_standard_concentration_span",
                    "sse",
                    "rmse",
                    "r_squared",
                    "r_squared_reason",
                    "convergence_status",
                    "termination_reason",
                    "parameter_boundary_flags",
                    "jacobian_rank",
                    "jacobian_condition_number",
                    "jacobian_scale_description",
                    "midpoint_within_observed_positive_span",
                )
            },
            "raw_standard_records": standard_records,
            "fit_levels": fit_levels,
            "residuals": residuals,
            "source_record_references": curve_result.source_record_references,
            "inverse": inverse_payload,
        },
        "charts": chart_names,
        "limitations": [
            "This report does not refit the curve or calculate any unknown-sample value.",
            "curve_validated=false and validated_quantification_enabled=false.",
            (
                "The observed positive concentration span is not an LLOQ, ULOQ, "
                "or validated quantification range."
            ),
            (
                "Research-only sample estimates, when present, are per measurement "
                "and not validated quantification."
            ),
        ],
    }
    return data, {"configuration": configuration, "sources": sources, "report_id": report_id}


def _bundled_node() -> Path:
    configured = os.environ.get("BIOLAB_REPORT_NODE")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise ReportRenderError("The bundled Node.js runtime for XLSX rendering is unavailable.")


def _bundled_python() -> Path:
    configured = os.environ.get("BIOLAB_REPORT_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"),
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise ReportRenderError("A Python runtime for DOCX rendering is unavailable.")


def _render_xlsx(data_path: Path, output_path: Path, chart_dir: Path) -> None:
    script = Path(__file__).resolve().parents[3] / "scripts" / "report_workbook.mjs"
    try:
        qa_dir = output_path.parent.parent / f".qa-{data_path.stem}-{data_path.parent.name}"
        completed = subprocess.run(
            [
                _bundled_node(),
                str(script),
                str(data_path),
                str(output_path),
                str(chart_dir),
                str(qa_dir),
            ],
            cwd=script.parent.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ReportRenderError(f"XLSX renderer could not start: {exc}") from exc
    if completed.returncode != 0:
        raise ReportRenderError(f"XLSX renderer failed: {completed.stderr[-2000:]}")


def _render_docx(data_path: Path, output_path: Path, chart_dir: Path) -> None:
    script = Path(__file__).resolve().parents[3] / "scripts" / "report_docx.py"
    try:
        completed = subprocess.run(
            [_bundled_python(), str(script), str(data_path), str(chart_dir), str(output_path)],
            cwd=script.parent.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ReportRenderError(f"DOCX renderer could not start: {exc}") from exc
    if completed.returncode != 0:
        raise ReportRenderError(f"DOCX renderer failed: {completed.stderr[-2000:]}")


def _write_manifest(
    *,
    output_dir: Path,
    report_type: str,
    report_id: str,
    sources: dict[str, str],
    configuration: dict[str, Any],
    warnings: list[dict[str, Any]],
) -> Path:
    output_files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == "report_manifest.json":
            continue
        relative = path.relative_to(output_dir).as_posix()
        artifact_type = "chart" if relative.startswith("charts/") else path.stem
        from biolab_copilot.contracts import ArtifactFile

        output_files.append(
            ArtifactFile(
                path=relative,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                artifact_type=artifact_type,
            )
        )
    manifest = ReportManifest(
        report_id=report_id,
        report_type=report_type,  # type: ignore[arg-type]
        status="COMPLETED",
        source_manifests={"upstream": sources.get("upstream_manifest", "")},
        source_artifacts=sources,
        configuration=configuration,
        software_versions={
            "biolab_copilot": __version__,
            "python": platform.python_version(),
            "matplotlib": matplotlib.__version__,
            "docx_renderer": "python-docx",
            "xlsx_renderer": "@oai/artifact-tool",
        },
        output_files=output_files,
        warnings=[],
        created_at=datetime.now(UTC),
    )
    path = output_dir / "report_manifest.json"
    _json_dump(path, manifest.model_dump(mode="json"))
    return path


def _render_package(
    *,
    data: dict[str, Any],
    metadata: dict[str, Any],
    output_dir: Path,
) -> Path:
    output = output_dir.resolve()
    if not output.is_dir() or not (output / "charts").is_dir():
        raise ReportRenderError("Report output directory was not prepared correctly.")
    data_path = output / "report_data.json"
    _json_dump(data_path, data)
    _render_xlsx(data_path, output / "report.xlsx", output / "charts")
    _render_docx(data_path, output / "report.docx", output / "charts")
    return _write_manifest(
        output_dir=output,
        report_type=str(data["report_type"]),
        report_id=str(metadata["report_id"]),
        sources=dict(metadata["sources"]),
        configuration=dict(metadata["configuration"]),
        warnings=list(data["qc"]["issues"]),
    )


def render_generic_report(analysis_dir: Path, output_dir: Path) -> Path:
    try:
        package = load_generic_package(analysis_dir)
        output = _new_output_dir(output_dir)
        result = package.result
        assert isinstance(result, AnalysisResult)
        data_stub, _ = _generic_data(package, [])
        chart_path = output / "charts" / "generic_measurements.png"
        render_generic_chart(
            raw_points=data_stub["results"]["measurements"],
            group_statistics=data_stub["results"]["group_statistics"],
            unit=package.plan.declared_units.get(package.plan.measurement_field, ""),
            path=chart_path,
        )
        data, metadata = _generic_data(package, ["charts/generic_measurements.png"])
        return _render_package(data=data, metadata=metadata, output_dir=output)
    except (UpstreamValidationError, OSError, ValueError) as exc:
        raise ReportRenderError(str(exc)) from exc


def render_welch_report(analysis_dir: Path, output_dir: Path) -> Path:
    try:
        package, preview = load_welch_package(analysis_dir)
        output = _new_output_dir(output_dir)
        data_stub, _ = _welch_data(package, preview, [])
        chart_path = output / "charts" / "welch_experimental_units.png"
        unit = package.plan.declared_units.get(package.plan.measurement_field, "")
        render_welch_chart(
            unit_values=data_stub["results"]["experimental_units"],
            group_statistics=data_stub["results"]["group_statistics"],
            unit=unit,
            path=chart_path,
        )
        data, metadata = _welch_data(package, preview, ["charts/welch_experimental_units.png"])
        return _render_package(data=data, metadata=metadata, output_dir=output)
    except (UpstreamValidationError, OSError, ValueError) as exc:
        raise ReportRenderError(str(exc)) from exc


def render_elisa_report(
    curve_dir: Path,
    output_dir: Path,
    inverse_dir: Path | None = None,
) -> Path:
    try:
        curve, standards = load_elisa_curve_package(curve_dir)
        inverse = load_elisa_inverse_package(inverse_dir) if inverse_dir is not None else None
        if inverse is not None:
            validate_elisa_inverse_binding(curve, inverse)
        output = _new_output_dir(output_dir)
        curve_payload = _model_payload(curve.result)
        standard_records = [_model_payload(item) for item in standards.records]
        curve_chart = output / "charts" / "elisa_4pl_curve.png"
        residual_chart = output / "charts" / "elisa_4pl_residuals.png"
        render_elisa_curve_chart(
            curve=curve_payload,
            standard_records=standard_records,
            path=curve_chart,
        )
        render_elisa_residual_chart(curve=curve_payload, path=residual_chart)
        chart_names = ["charts/elisa_4pl_curve.png", "charts/elisa_4pl_residuals.png"]
        if inverse is not None:
            inverse_payload = _model_payload(inverse.result)
            status_chart = output / "charts" / "elisa_sample_status_counts.png"
            render_status_counts_chart(records=inverse_payload["records"], path=status_chart)
            chart_names.append("charts/elisa_sample_status_counts.png")
        data, metadata = _elisa_data(curve, standards, inverse, chart_names)
        return _render_package(data=data, metadata=metadata, output_dir=output)
    except (UpstreamValidationError, OSError, ValueError) as exc:
        raise ReportRenderError(str(exc)) from exc


__all__ = [
    "ReportRenderError",
    "render_elisa_report",
    "render_generic_report",
    "render_welch_report",
]
