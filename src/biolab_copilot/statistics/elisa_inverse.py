"""Research-only, per-measurement inverse estimation for a confirmed 4PL curve."""

from __future__ import annotations

import json
import math
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from biolab_copilot.contracts import (
    AnalysisPlan,
    CurveFitResult,
    ELISAInverseDesign,
    ExcludedSampleRecord,
    ImportResult,
    InverseRunStatus,
    InverseStatus,
    IssueSeverity,
    RunManifest,
    SampleConcentrationPreview,
    SampleConcentrationRecord,
    SampleConcentrationsResult,
    ValidationIssue,
)
from biolab_copilot.ingestion import sha256_file
from biolab_copilot.statistics.elisa_4pl import four_pl_predict

INVERSE_LIMITATIONS = [
    "This is a research-only numerical estimate, not validated assay quantification.",
    "curve_validated=false and validated_quantification_enabled=false are immutable semantics.",
    (
        "Unknown sample records are processed independently; no replicate aggregation, CV, "
        "or SD is calculated."
    ),
    (
        "The allowed concentration span is an interpolation guard, not an LLOQ, ULOQ, or "
        "validated range."
    ),
    (
        "No blank correction, dilution-factor inference, unit conversion, 5PL fit, or "
        "extrapolation is performed."
    ),
]


@dataclass(frozen=True)
class CurveAssets:
    result_path: Path
    plan_path: Path
    preview_path: Path
    manifest_path: Path
    result: CurveFitResult | None
    plan: AnalysisPlan | None
    manifest: RunManifest | None
    result_sha256: str
    plan_sha256: str
    preview_sha256: str
    manifest_sha256: str
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class InversePlanBuild:
    plan: AnalysisPlan
    preview: SampleConcentrationPreview
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class InverseExecutionPreflight:
    plan: AnalysisPlan
    design: ELISAInverseDesign | None
    curve: CurveAssets
    sample_import: ImportResult | None
    preview: SampleConcentrationPreview | None
    plan_sha256: str
    sample_artifact_sha256: str | None
    issues: tuple[ValidationIssue, ...]


def _issue(
    code: str,
    message: str,
    suggested_action: str,
    *,
    severity: IssueSeverity = IssueSeverity.BLOCKING,
    location: str = "analysis_plan",
    record: Any | None = None,
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        location=location if record is None else _source_location(record),
        suggested_action=suggested_action,
        source_file=None if record is None else record.source_file,
        sheet_name=None if record is None else record.sheet_name,
        record_number=None if record is None else record.record_number,
        source_row_number=None if record is None else record.source_row_number,
        field=field,
        raw_value=None if raw_value is None else str(raw_value)[:200],
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_import(path: Path) -> tuple[ImportResult | None, list[ValidationIssue]]:
    try:
        return ImportResult.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "SAMPLE_ARTIFACT_INVALID",
                f"The bound ELISA import artifact is invalid: {type(exc).__name__}.",
                "Use an unchanged imported_data.json produced by the Phase 1 import CLI.",
                location=f"file={path.name}",
            )
        ]


def _load_design(path: Path) -> tuple[ELISAInverseDesign | None, list[ValidationIssue]]:
    try:
        return ELISAInverseDesign.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "INVERSE_DESIGN_INVALID",
                f"The inverse design declaration is invalid: {type(exc).__name__}.",
                "Provide explicit research-use, context, and dilution declarations.",
                location=f"file={path.name}",
            )
        ]


def _load_plan(path: Path) -> tuple[AnalysisPlan | None, list[ValidationIssue]]:
    try:
        return AnalysisPlan.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "CURVE_PLAN_INVALID",
                f"The bound Phase 3A plan is invalid: {type(exc).__name__}.",
                "Use the unchanged Phase 3A analysis_plan.json.",
                location=f"file={path.name}",
            )
        ]


def _load_result(path: Path) -> tuple[CurveFitResult | None, list[ValidationIssue]]:
    try:
        return CurveFitResult.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "CURVE_RESULT_INVALID",
                f"The bound Phase 3A curve result is invalid: {type(exc).__name__}.",
                "Use an unchanged curve_fit_result.json from a completed Phase 3A run.",
                location=f"file={path.name}",
            )
        ]


def _load_manifest(path: Path) -> tuple[RunManifest | None, list[ValidationIssue]]:
    try:
        return RunManifest.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "CURVE_MANIFEST_INVALID",
                f"The Phase 3A run manifest is invalid: {type(exc).__name__}.",
                "Use the unchanged run_manifest.json from the curve run.",
                location=f"file={path.name}",
            )
        ]


def _source_location(record: Any) -> str:
    return next(iter(record.source_locations.values()), f"record={record.record_number}")


def _raw(record: Any, field: str, mapping: dict[str, str]) -> Any:
    source = next((key for key, value in mapping.items() if value == field), field)
    return record.raw_values.get(source)


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:200]


def _resolve_path(
    raw: str | None, allowed_root: Path, code: str, label: str
) -> tuple[Path | None, list[ValidationIssue]]:
    if not raw:
        return None, [
            _issue(
                f"{code}_MISSING",
                f"The plan does not bind a {label}.",
                f"Regenerate the inverse plan with a bound {label}.",
            )
        ]
    path = Path(raw).resolve()
    try:
        path.relative_to(allowed_root.resolve())
    except ValueError:
        return None, [
            _issue(
                f"{code}_OUTSIDE_PROJECT",
                f"The bound {label} is outside the project.",
                "Use a project-local artifact.",
                location=f"file={path}",
            )
        ]
    if not path.is_file():
        return None, [
            _issue(
                f"{code}_NOT_FOUND",
                f"The bound {label} is unavailable.",
                f"Restore the unchanged {label}.",
                location=f"file={path}",
            )
        ]
    return path, []


def _curve_assets(
    result_path: Path,
    *,
    plan_path: Path | None = None,
    preview_path: Path | None = None,
    manifest_path: Path | None = None,
    allowed_root: Path | None = None,
) -> CurveAssets:
    result_path = result_path.resolve()
    root = (allowed_root or result_path.parents[2]).resolve()
    plan_path = (plan_path or result_path.parent / "analysis_plan.json").resolve()
    preview_path = (preview_path or result_path.parent / "standards_preview.json").resolve()
    manifest_path = (manifest_path or result_path.parent / "run_manifest.json").resolve()
    issues: list[ValidationIssue] = []
    inside_paths: set[Path] = set()
    for path, code, label in (
        (result_path, "CURVE_RESULT", "curve result"),
        (plan_path, "CURVE_PLAN", "curve plan"),
        (preview_path, "CURVE_PREVIEW", "standards preview"),
        (manifest_path, "CURVE_MANIFEST", "curve manifest"),
    ):
        try:
            path.relative_to(root)
            inside_paths.add(path)
        except ValueError:
            issues.append(
                _issue(
                    f"{code}_OUTSIDE_PROJECT",
                    f"The {label} is outside the project.",
                    "Use project-local Phase 3A artifacts.",
                    location=f"file={path}",
                )
            )
        if not path.is_file():
            issues.append(
                _issue(
                    f"{code}_NOT_FOUND",
                    f"The {label} is unavailable.",
                    "Use a complete Phase 3A run directory.",
                    location=f"file={path}",
                )
            )
    result, result_issues = (
        _load_result(result_path)
        if result_path in inside_paths and result_path.is_file()
        else (None, [])
    )
    plan, plan_issues = (
        _load_plan(plan_path) if plan_path in inside_paths and plan_path.is_file() else (None, [])
    )
    manifest, manifest_issues = (
        _load_manifest(manifest_path)
        if manifest_path in inside_paths and manifest_path.is_file()
        else (None, [])
    )
    issues.extend(result_issues)
    issues.extend(plan_issues)
    issues.extend(manifest_issues)
    result_sha = (
        sha256_file(result_path)
        if result_path in inside_paths and result_path.is_file()
        else "0" * 64
    )
    plan_sha = (
        sha256_file(plan_path) if plan_path in inside_paths and plan_path.is_file() else "0" * 64
    )
    preview_sha = (
        sha256_file(preview_path)
        if preview_path in inside_paths and preview_path.is_file()
        else "0" * 64
    )
    manifest_sha = (
        sha256_file(manifest_path)
        if manifest_path in inside_paths and manifest_path.is_file()
        else "0" * 64
    )
    if result is not None:
        if result.status != "computed":
            issues.append(
                _issue(
                    "CURVE_RESULT_NOT_COMPUTED",
                    "The Phase 3A curve result is not computed.",
                    "Use a successfully converged Phase 3A standard-only result.",
                )
            )
        if result.curve_validated is not False or result.quantification_enabled is not False:
            issues.append(
                _issue(
                    "CURVE_RESULT_SEMANTICS_INVALID",
                    "The curve result does not preserve Phase 3A non-validation semantics.",
                    "Do not edit result flags; use an unchanged Phase 3A result.",
                )
            )
        if result.convergence_status != "converged_candidate_selected":
            issues.append(
                _issue(
                    "CURVE_NOT_CONVERGED",
                    "The Phase 3A optimizer did not select a converged candidate.",
                    "Do not perform inverse estimation from this curve.",
                )
            )
        if result.jacobian_rank is None or result.jacobian_rank < 4:
            issues.append(
                _issue(
                    "CURVE_JACOBIAN_RANK_DEFICIENT",
                    "The curve Jacobian is rank deficient or unavailable.",
                    "Do not perform inverse estimation from this numerically unidentifiable curve.",
                )
            )
        threshold = (
            1e10
            if plan is None
            else plan.diagnostic_thresholds.get("jacobian_condition_threshold", 1e10)
        )
        if (
            result.jacobian_condition_number is None
            or not math.isfinite(result.jacobian_condition_number)
            or result.jacobian_condition_number >= threshold
        ):
            issues.append(
                _issue(
                    "CURVE_JACOBIAN_ILL_CONDITIONED",
                    "The curve Jacobian is severely ill-conditioned by the Phase 3A threshold.",
                    "Do not perform inverse estimation from this curve.",
                )
            )
        if any(result.parameter_boundary_flags.values()):
            issues.append(
                _issue(
                    "CURVE_PARAMETER_NEAR_BOUNDARY",
                    "At least one fitted parameter is near a configured numerical boundary.",
                    "Do not perform inverse estimation from a boundary-limited curve.",
                )
            )
        if any(
            issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
            for issue in result.issues
        ):
            issues.append(
                _issue(
                    "CURVE_RESULT_HAS_BLOCKING_ISSUES",
                    "The Phase 3A result contains error or blocking diagnostics.",
                    "Resolve the curve diagnostics before inverse estimation.",
                )
            )
    if plan is not None:
        if (
            plan.assay_type != "elisa_standard_curve"
            or plan.analysis_level != "standard_curve_levels"
        ):
            issues.append(
                _issue(
                    "UNSUPPORTED_CURVE_PLAN",
                    "The bound plan is not a Phase 3A ELISA standard-curve plan.",
                    "Bind a Phase 3A 4PL standard-only plan.",
                )
            )
        if result is not None and result.confirmed_plan_sha256 != plan_sha:
            issues.append(
                _issue(
                    "CURVE_PLAN_HASH_MISMATCH",
                    "The curve result was not produced from the current Phase 3A plan bytes.",
                    "Use matching, unchanged curve artifacts.",
                )
            )
        if plan.standards_preview_sha256 != preview_sha:
            issues.append(
                _issue(
                    "CURVE_PREVIEW_HASH_MISMATCH",
                    "The standards preview hash does not match the current preview file.",
                    "Use matching, unchanged curve artifacts.",
                )
            )
        input_path = Path(plan.input_artifact_path).resolve() if plan.input_artifact_path else None
        input_inside = False
        if input_path is not None:
            try:
                input_path.relative_to(root)
                input_inside = True
            except ValueError:
                issues.append(
                    _issue(
                        "CURVE_INPUT_ARTIFACT_OUTSIDE_PROJECT",
                        "The Phase 3A plan points to an input artifact outside the project.",
                        "Use a project-local Phase 3A import artifact.",
                    )
                )
        if (
            input_inside
            and input_path is not None
            and input_path.is_file()
            and plan.input_artifact_sha256 != sha256_file(input_path)
        ):
            issues.append(
                _issue(
                    "CURVE_INPUT_ARTIFACT_HASH_MISMATCH",
                    "The Phase 3A import artifact changed.",
                    "Regenerate the curve and inverse plans.",
                )
            )
    if result is not None and result.standards_preview_sha256 != preview_sha:
        issues.append(
            _issue(
                "CURVE_RESULT_PREVIEW_HASH_MISMATCH",
                "The curve result does not match the current standards preview.",
                "Use matching, unchanged curve artifacts.",
            )
        )
    if (
        result is not None
        and plan is not None
        and result.input_artifact_sha256 != plan.input_artifact_sha256
    ):
        issues.append(
            _issue(
                "CURVE_RESULT_INPUT_HASH_MISMATCH",
                "The curve result does not bind the current Phase 3A input artifact.",
                "Use matching, unchanged Phase 3A artifacts.",
            )
        )
    if manifest is not None:
        if (
            manifest.analysis_plan_sha256 != plan_sha
            or manifest.preview_sha256 != preview_sha
            or manifest.standards_preview_sha256 != preview_sha
        ):
            issues.append(
                _issue(
                    "CURVE_MANIFEST_HASH_MISMATCH",
                    "The Phase 3A manifest does not match the plan or preview bytes.",
                    "Use matching, unchanged curve artifacts.",
                )
            )
        if manifest.curve_validated is not False or manifest.quantification_enabled is not False:
            issues.append(
                _issue(
                    "CURVE_MANIFEST_SEMANTICS_INVALID",
                    "The Phase 3A manifest does not preserve non-validation semantics.",
                    "Use an unchanged Phase 3A manifest.",
                )
            )
        output_hashes = {Path(item.path).resolve(): item.sha256 for item in manifest.output_files}
        if output_hashes.get(result_path) != result_sha:
            issues.append(
                _issue(
                    "CURVE_RESULT_MANIFEST_HASH_MISMATCH",
                    "The manifest hash for curve_fit_result.json is missing or stale.",
                    "Use the unchanged Phase 3A run directory.",
                )
            )
        if (
            output_hashes.get(plan_path) != plan_sha
            or output_hashes.get(preview_path) != preview_sha
        ):
            issues.append(
                _issue(
                    "CURVE_ARTIFACT_MANIFEST_HASH_MISMATCH",
                    "The manifest does not bind the current Phase 3A plan and preview.",
                    "Use the unchanged Phase 3A run directory.",
                )
            )
    return CurveAssets(
        result_path,
        plan_path,
        preview_path,
        manifest_path,
        result,
        plan,
        manifest,
        result_sha,
        plan_sha,
        preview_sha,
        manifest_sha,
        tuple(issues),
    )


def _sample_type(record: Any) -> str:
    value = record.parsed_values.get("sample_type")
    return "" if value is None else str(value).strip().lower()


def _inverse_one(
    response: float,
    factor: float,
    curve: CurveFitResult,
    design: ELISAInverseDesign,
    span: tuple[float, float],
    response_span: tuple[float, float],
) -> tuple[InverseStatus, float | None, float | None, str]:
    lower = curve.lower_asymptote
    upper = curve.upper_asymptote
    midpoint = curve.midpoint_concentration
    slope = curve.slope_magnitude
    if any(value is None for value in (lower, upper, midpoint, slope)):
        return (
            "numerical_failure",
            None,
            None,
            "The curve result does not contain four finite parameters.",
        )
    assert lower is not None and upper is not None and midpoint is not None and slope is not None
    if not all(math.isfinite(value) for value in (response, factor, lower, upper, midpoint, slope)):
        return (
            "numerical_failure",
            None,
            None,
            "The response, dilution factor, or curve parameters are non-finite.",
        )
    scale = max(abs(upper - lower), 1.0)
    distance_to_asymptote = min(abs(response - lower), abs(upper - response))
    if response <= lower or response >= upper:
        if distance_to_asymptote <= design.asymptote_tolerance * scale:
            return (
                "near_asymptote_unstable",
                None,
                None,
                "The response is at or numerically near a 4PL asymptote.",
            )
        return (
            "outside_model_domain",
            None,
            None,
            "The response is outside the open 4PL model domain L<y<U.",
        )
    if distance_to_asymptote <= design.asymptote_tolerance * scale:
        return (
            "near_asymptote_unstable",
            None,
            None,
            "The response is numerically near a 4PL asymptote.",
        )
    try:
        sign = 1.0 if curve.direction == "increasing" else -1.0
        log_x = math.log(midpoint) + (sign / slope) * (
            math.log(response - lower) - math.log(upper - response)
        )
        if (
            not math.isfinite(log_x)
            or log_x > design.log_overflow_threshold
            or log_x < math.log(sys.float_info.min)
        ):
            return (
                "numerical_failure",
                None,
                None,
                "Protected inverse exponentiation would be non-finite or outside float64 range.",
            )
        assayed = math.exp(log_x)
        if not math.isfinite(assayed) or assayed <= 0:
            return (
                "numerical_failure",
                None,
                None,
                "The inverse concentration is non-finite or non-positive.",
            )
        tolerance = design.concentration_tolerance * max(span[1], 1.0)
        if assayed < span[0] - tolerance:
            return (
                "below_standard_span",
                None,
                None,
                "The inferred concentration is below the positive standard span; "
                "extrapolation is disabled.",
            )
        if assayed > span[1] + tolerance:
            return (
                "above_standard_span",
                None,
                None,
                "The inferred concentration is above the positive standard span; "
                "extrapolation is disabled.",
            )
        if abs(assayed - span[0]) <= tolerance:
            assayed = span[0]
        elif abs(assayed - span[1]) <= tolerance:
            assayed = span[1]
        predicted = four_pl_predict(assayed, lower, upper, midpoint, slope, curve.direction)
        if abs(predicted - response) > design.forward_check_tolerance * max(
            1.0, abs(response), scale
        ):
            return (
                "numerical_failure",
                None,
                None,
                "Forward substitution did not reproduce the input response within the "
                "configured tolerance.",
            )
        original = assayed * factor
        if not math.isfinite(original):
            return (
                "numerical_failure",
                assayed,
                None,
                "Dilution correction overflowed or became non-finite.",
            )
        return (
            "estimated_within_standard_span",
            assayed,
            original,
            "Finite interpolation estimate with forward-substitution agreement.",
        )
    except (FloatingPointError, OverflowError, ValueError, ZeroDivisionError) as exc:
        return (
            "numerical_failure",
            None,
            None,
            f"Protected inverse calculation failed: {type(exc).__name__}.",
        )


def _build_sample_preview(
    curve: CurveFitResult,
    sample_import: ImportResult,
    design: ELISAInverseDesign,
    *,
    curve_result_sha256: str,
    sample_artifact_sha256: str,
) -> tuple[SampleConcentrationPreview, list[ValidationIssue], list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    blockers: list[ValidationIssue] = []
    if curve.observed_standard_concentration_span is None:
        blocker = _issue(
            "CURVE_SPAN_MISSING",
            "The curve result has no positive standard concentration span.",
            "Use a completed Phase 3A curve with a finite positive span.",
        )
        return (
            SampleConcentrationPreview(
                preview_id=f"inverse-preview-{sample_artifact_sha256[:12]}",
                curve_fit_result_sha256=curve_result_sha256,
                sample_artifact_sha256=sample_artifact_sha256,
                preview_ready=False,
                blocking_reasons=[blocker],
            ),
            [],
            [blocker],
        )
    span = curve.observed_standard_concentration_span
    lower = curve.lower_asymptote
    upper = curve.upper_asymptote
    midpoint = curve.midpoint_concentration
    slope = curve.slope_magnitude
    if any(value is None for value in (lower, upper, midpoint, slope)):
        blocker = _issue(
            "CURVE_PARAMETERS_INVALID",
            "The curve parameters are not finite and constrained for inverse estimation.",
            "Use a valid converged Phase 3A curve result.",
        )
        return (
            SampleConcentrationPreview(
                preview_id=f"inverse-preview-{sample_artifact_sha256[:12]}",
                curve_fit_result_sha256=curve_result_sha256,
                sample_artifact_sha256=sample_artifact_sha256,
                preview_ready=False,
                blocking_reasons=[blocker],
            ),
            [],
            [blocker],
        )
    assert lower is not None and upper is not None and midpoint is not None and slope is not None
    if not all(math.isfinite(value) for value in (lower, upper, midpoint, slope)) or not (
        upper > lower and midpoint > 0 and slope > 0
    ):
        blocker = _issue(
            "CURVE_PARAMETERS_INVALID",
            "The curve parameters are not finite and constrained for inverse estimation.",
            "Use a valid converged Phase 3A curve result.",
        )
        return (
            SampleConcentrationPreview(
                preview_id=f"inverse-preview-{sample_artifact_sha256[:12]}",
                curve_fit_result_sha256=curve_result_sha256,
                sample_artifact_sha256=sample_artifact_sha256,
                preview_ready=False,
                blocking_reasons=[blocker],
            ),
            [],
            [blocker],
        )
    y_min = four_pl_predict(span[0], lower, upper, midpoint, slope, curve.direction)
    y_max = four_pl_predict(span[1], lower, upper, midpoint, slope, curve.direction)
    response_span = (min(y_min, y_max), max(y_min, y_max))
    records: list[SampleConcentrationRecord] = []
    excluded: list[ExcludedSampleRecord] = []
    sample_rows = [record for record in sample_import.records if _sample_type(record) == "sample"]
    if not sample_rows:
        blocker = _issue(
            "NO_SAMPLE_ROWS",
            "The bound import artifact contains no sample rows.",
            "Provide at least one row with sample_type=sample.",
        )
        blockers.append(blocker)
    for record in sample_import.records:
        if _sample_type(record) != "sample":
            excluded.append(
                ExcludedSampleRecord(
                    record_number=record.record_number,
                    sample_type=record.parsed_values.get("sample_type"),
                    source_location=_source_location(record),
                    reason=(
                        "Only sample rows are eligible for inverse estimation; the source row "
                        "is retained."
                    ),
                )
            )
            continue
        response_raw = record.parsed_values.get("measurement")
        response = (
            float(response_raw)
            if isinstance(response_raw, int | float) and not isinstance(response_raw, bool)
            else None
        )
        factor_raw = (
            design.uniform_dilution_factor
            if design.dilution_factor_source == "uniform_declared"
            else record.parsed_values.get("dilution_factor")
        )
        factor = (
            float(factor_raw)
            if isinstance(factor_raw, int | float)
            and not isinstance(factor_raw, bool)
            and math.isfinite(float(factor_raw))
            else None
        )
        measurement_id = f"record-{record.record_number}"
        common: dict[str, Any] = dict(
            record_number=record.record_number,
            measurement_id=measurement_id,
            sample_id=record.parsed_values.get("sample_id"),
            replicate_type=record.parsed_values.get("replicate_type"),
            replicate_id=record.parsed_values.get("replicate_id"),
            source_file=record.source_file,
            sheet_name=record.sheet_name,
            source_row_number=record.source_row_number,
            source_location=_source_location(record),
            raw_response=_safe_text(_raw(record, "measurement", sample_import.column_mapping)),
            response=response,
            dilution_factor=factor,
            curve_response_lower=response_span[0],
            curve_response_upper=response_span[1],
        )
        if response is None or not math.isfinite(response):
            reason = "The sample response is missing or non-finite; no concentration was filled in."
            issue = _issue(
                "SAMPLE_RESPONSE_INVALID",
                reason,
                "Resolve the response without imputation.",
                severity=IssueSeverity.ERROR,
                record=record,
                field="measurement",
                raw_value=_raw(record, "measurement", sample_import.column_mapping),
            )
            issues.append(issue)
            records.append(
                SampleConcentrationRecord(**common, status="numerical_failure", reason=reason)
            )
            continue
        if factor is None or factor < 1:
            reason = (
                "The sample dilution factor is missing, non-finite, or below 1; no default "
                "was used."
            )
            issue = _issue(
                "DILUTION_FACTOR_INVALID",
                reason,
                "Provide an explicit finite dilution_factor >= 1.",
                severity=IssueSeverity.ERROR,
                record=record,
                field="dilution_factor",
                raw_value=_raw(record, "dilution_factor", sample_import.column_mapping),
            )
            issues.append(issue)
            records.append(
                SampleConcentrationRecord(**common, status="numerical_failure", reason=reason)
            )
            continue
        status, assayed, original, reason = _inverse_one(
            response, factor, curve, design, span, response_span
        )
        severity = (
            IssueSeverity.WARNING
            if status in {"below_standard_span", "above_standard_span", "near_asymptote_unstable"}
            else IssueSeverity.ERROR
            if status in {"outside_model_domain", "numerical_failure"}
            else None
        )
        if severity is not None:
            code = (
                "SAMPLE_OUTSIDE_STANDARD_SPAN"
                if status in {"below_standard_span", "above_standard_span"}
                else "SAMPLE_NEAR_ASYMPTOTE"
                if status == "near_asymptote_unstable"
                else "SAMPLE_INVERSE_NUMERICAL_FAILURE"
            )
            issues.append(
                _issue(
                    code,
                    reason,
                    "Review the retained row diagnostic; do not substitute a concentration.",
                    severity=severity,
                    record=record,
                    field="measurement",
                    raw_value=response,
                )
            )
        records.append(
            SampleConcentrationRecord(
                **common,
                concentration_in_assayed_sample=assayed,
                concentration_in_original_sample=original,
                status=status,
                reason=reason,
            )
        )
    preview = SampleConcentrationPreview(
        preview_id=f"inverse-preview-{sample_artifact_sha256[:12]}",
        curve_fit_result_sha256=curve_result_sha256,
        sample_artifact_sha256=sample_artifact_sha256,
        records=records,
        excluded_records=excluded,
        warnings=[item for item in issues if item.severity == IssueSeverity.WARNING],
        blocking_reasons=[
            *blockers,
            *[
                item
                for item in issues
                if item.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
            ],
        ],
        preview_ready=not blockers,
    )
    return preview, issues, blockers


def _required_confirmation_codes(
    curve: CurveFitResult,
    preview: SampleConcentrationPreview,
    sample_import: ImportResult | None = None,
) -> list[str]:
    codes = {
        f"CURVE_WARNING_{issue.code}"
        for issue in curve.issues
        if issue.severity == IssueSeverity.WARNING
    }
    if any(
        record.status in {"below_standard_span", "above_standard_span"}
        for record in preview.records
    ):
        codes.add("SAMPLE_OUTSIDE_STANDARD_SPAN")
    if any(record.status == "near_asymptote_unstable" for record in preview.records):
        codes.add("SAMPLE_NEAR_ASYMPTOTE")
    if sample_import is not None:
        codes.update(
            f"SAMPLE_IMPORT_WARNING_{issue.code}"
            for issue in sample_import.validation_issues
            if issue.severity == IssueSeverity.WARNING
        )
    return sorted(codes)


def _basic_plan(
    *,
    sample_path: Path | None,
    sample_import: ImportResult | None,
    design_path: Path,
    design: ELISAInverseDesign | None,
    curve: CurveAssets,
    preview_path: Path,
    preview_sha: str | None,
    required: list[str],
) -> AnalysisPlan:
    curve_result = curve.result
    sample_sha = (
        sha256_file(sample_path) if sample_path is not None and sample_path.is_file() else None
    )
    source_sha = sample_import.input_file.sha256 if sample_import is not None else None
    concentration_unit = (
        curve_result.concentration_unit if curve_result is not None else "unspecified"
    )
    response_unit = curve_result.response_unit if curve_result is not None else "unspecified"
    return AnalysisPlan(
        plan_id=(
            f"plan-inverse-{(sample_sha or curve.result_sha256)[:12]}-{curve.result_sha256[:12]}"
        ),
        experiment_id=(
            sample_import.dataset_profile.dataset_id
            if sample_import is not None
            else "invalid-inverse-plan"
        ),
        assay_type="elisa_standard_curve",
        objectives=[
            "Estimate research-use unknown sample concentrations per measurement row from "
            "an unchanged Phase 3A 4PL result."
        ],
        requested_outputs=[
            "analysis_plan",
            "sample_concentrations",
            "analysis_issues",
            "run_manifest",
        ],
        configuration=sample_import.parse_configuration if sample_import is not None else {},
        confirmed=False,
        input_artifact_path=str(sample_path.resolve()) if sample_path is not None else None,
        input_artifact_sha256=sample_sha,
        source_sha256=source_sha,
        column_mapping=sample_import.column_mapping if sample_import is not None else {},
        declared_units={"standard_concentration": concentration_unit, "measurement": response_unit},
        group_field="sample_type",
        measurement_field="measurement",
        analysis_level="measurement_rows",
        statistics=[],
        required_confirmations=required,
        warning_confirmations={
            code: bool(design and design.warning_confirmations.get(code) is True)
            for code in required
        },
        generated_at=datetime.now(UTC),
        inverse_curve_fit_result_path=str(curve.result_path),
        inverse_curve_fit_result_sha256=curve.result_sha256,
        inverse_curve_plan_path=str(curve.plan_path),
        inverse_curve_plan_sha256=curve.plan_sha256,
        inverse_curve_preview_path=str(curve.preview_path),
        inverse_curve_preview_sha256=curve.preview_sha256,
        inverse_curve_manifest_path=str(curve.manifest_path),
        inverse_curve_manifest_sha256=curve.manifest_sha256,
        inverse_design_path=str(design_path.resolve()),
        inverse_design_sha256=sha256_file(design_path),
        inverse_method="four_parameter_logistic_inverse",
        inverse_sample_artifact_path=str(sample_path.resolve())
        if sample_path is not None
        else None,
        inverse_sample_artifact_sha256=sample_sha,
        inverse_sample_source_sha256=source_sha,
        inverse_sample_column_mapping=sample_import.column_mapping
        if sample_import is not None
        else {},
        inverse_sample_parse_configuration=sample_import.parse_configuration
        if sample_import is not None
        else {},
        intended_use=design.intended_use if design else "research_only",
        research_only_acknowledged=True if design else None,
        validated_quantification_enabled=False if design else None,
        research_estimation_enabled=True if design else None,
        curve_context_compatibility_declared=True if design else None,
        curve_context_compatibility_rationale=design.curve_context_compatibility_rationale
        if design
        else None,
        sample_source_mode=design.sample_source_mode if design else None,
        dilution_factor_source=design.dilution_factor_source if design else None,
        dilution_factor_field=design.dilution_factor_field if design else None,
        uniform_dilution_factor=design.uniform_dilution_factor if design else None,
        allow_extrapolation=False if design else None,
        inverse_numeric_settings={
            name: getattr(design, name)
            for name in (
                "response_tolerance",
                "asymptote_tolerance",
                "concentration_tolerance",
                "forward_check_tolerance",
                "log_overflow_threshold",
            )
        }
        if design
        else {},
        inverse_preview_path=str(preview_path.resolve()),
        inverse_preview_sha256=preview_sha,
    )


def build_inverse_plan(
    curve_result_path: Path,
    design_path: Path,
    preview_path: Path,
    *,
    allowed_root: Path,
) -> InversePlanBuild:
    """Build an unconfirmed inverse plan and deterministic sample preview."""
    curve = _curve_assets(curve_result_path, allowed_root=allowed_root)
    design_path = design_path.resolve()
    try:
        design_path.relative_to(allowed_root.resolve())
        design, design_issues = _load_design(design_path)
    except ValueError:
        design = None
        design_issues = [
            _issue(
                "INVERSE_DESIGN_OUTSIDE_PROJECT",
                "The inverse design declaration is outside the project.",
                "Use a project-local inverse design JSON file.",
                location=f"file={design_path}",
            )
        ]
    issues = [*curve.issues, *design_issues]
    if curve.result is not None:
        issues.extend(
            issue for issue in curve.result.issues if issue.severity == IssueSeverity.WARNING
        )
    sample_path: Path | None = None
    sample_import: ImportResult | None = None
    if design is not None:
        if design.sample_source_mode == "same_import_artifact":
            sample_path = (
                Path(curve.plan.input_artifact_path).resolve()
                if curve.plan and curve.plan.input_artifact_path
                else None
            )
        else:
            raw = (
                Path(design.sample_artifact_path).resolve() if design.sample_artifact_path else None
            )
            sample_path = raw
        if sample_path is not None:
            try:
                sample_path.relative_to(allowed_root.resolve())
            except ValueError:
                issues.append(
                    _issue(
                        "SAMPLE_ARTIFACT_OUTSIDE_PROJECT",
                        "The declared sample import artifact is outside the project.",
                        "Use a project-local imported_data.json.",
                        location=f"file={sample_path}",
                    )
                )
                sample_path = None
        if sample_path is not None:
            if not sample_path.is_file():
                issues.append(
                    _issue(
                        "SAMPLE_ARTIFACT_NOT_FOUND",
                        "The declared sample import artifact is unavailable.",
                        "Provide an unchanged project-local imported_data.json.",
                        location=f"file={sample_path}",
                    )
                )
            else:
                sample_import, sample_issues = _load_import(sample_path)
                issues.extend(sample_issues)
        else:
            issues.append(
                _issue(
                    "SAMPLE_ARTIFACT_MISSING",
                    "No sample import artifact is bound.",
                    "Declare same_import_artifact or provide a separate imported_data.json.",
                )
            )
    if sample_import is not None:
        if sample_import.experiment_type != "elisa_standard_curve":
            issues.append(
                _issue(
                    "UNSUPPORTED_SAMPLE_ASSAY",
                    "Inverse estimation accepts only ELISA import artifacts.",
                    "Use an elisa_standard_curve import artifact.",
                )
            )
        if not sample_import.analysis_ready or any(
            item.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
            for item in sample_import.validation_issues
        ):
            issues.append(
                _issue(
                    "SAMPLE_IMPORT_QC_NOT_READY",
                    "The sample import artifact contains error or blocking QC issues.",
                    "Resolve import QC before inverse estimation.",
                )
            )
        issues.extend(
            issue
            for issue in sample_import.validation_issues
            if issue.severity == IssueSeverity.WARNING
        )
    if design is not None and sample_import is not None and curve.result is not None:
        assert sample_path is not None
        if (
            curve.result.input_artifact_sha256
            != (curve.plan.input_artifact_sha256 if curve.plan else None)
            and design.sample_source_mode == "same_import_artifact"
        ):
            issues.append(
                _issue(
                    "CURVE_INPUT_BINDING_INVALID",
                    "The curve result and Phase 3A plan do not bind the same import artifact.",
                    "Regenerate the Phase 3A curve.",
                )
            )
        preview, preview_issues, preview_blockers = _build_sample_preview(
            curve.result,
            sample_import,
            design,
            curve_result_sha256=curve.result_sha256,
            sample_artifact_sha256=sha256_file(sample_path),
        )
        issues.extend(preview_issues)
    else:
        preview = SampleConcentrationPreview(
            preview_id=f"invalid-inverse-preview-{uuid.uuid4().hex[:8]}",
            curve_fit_result_sha256=curve.result_sha256,
            sample_artifact_sha256=sha256_file(sample_path)
            if sample_path and sample_path.is_file()
            else "0" * 64,
            preview_ready=False,
            blocking_reasons=[
                _issue(
                    "INVERSE_PREVIEW_UNAVAILABLE",
                    "A complete curve, design, and sample artifact are required to build "
                    "the preview.",
                    "Resolve the preceding diagnostics and regenerate the plan.",
                )
            ],
        )
        preview_issues = []
        preview_blockers = list(preview.blocking_reasons)
    required = (
        _required_confirmation_codes(curve.result, preview, sample_import)
        if curve.result is not None
        else []
    )
    plan = _basic_plan(
        sample_path=sample_path,
        sample_import=sample_import,
        design_path=design_path,
        design=design,
        curve=curve,
        preview_path=preview_path,
        preview_sha=None,
        required=required,
    )
    issues.extend(preview_blockers)
    return InversePlanBuild(plan=plan, preview=preview, issues=tuple(issues))


def _plan_placeholder() -> AnalysisPlan:
    return AnalysisPlan(
        plan_id="invalid-inverse-plan",
        experiment_id="invalid-inverse-plan",
        assay_type="elisa_standard_curve",
        objectives=["Invalid inverse plan"],
        analysis_level="measurement_rows",
        statistics=[],
    )


def validate_inverse_execution_inputs(
    plan_path: Path,
    confirmed_plan_sha256: str,
    *,
    allowed_root: Path,
) -> InverseExecutionPreflight:
    plan_sha = sha256_file(plan_path)
    try:
        plan = AnalysisPlan.model_validate(_load_json(plan_path))
        issues: list[ValidationIssue] = []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        plan = _plan_placeholder()
        issues = [
            _issue(
                "INVERSE_PLAN_INVALID",
                f"The inverse plan is invalid: {type(exc).__name__}.",
                "Use an unchanged plan generated by generate-elisa-inverse-plan.",
            )
        ]
    if confirmed_plan_sha256.lower() != plan_sha:
        issues.append(
            _issue(
                "PLAN_HASH_MISMATCH",
                "The explicit plan SHA-256 confirmation does not match the current plan.",
                "Confirm the exact unchanged plan SHA-256.",
            )
        )
    if not plan.confirmed:
        issues.append(
            _issue(
                "PLAN_NOT_CONFIRMED",
                "The inverse plan is not explicitly confirmed.",
                "Set confirmed=true only after reviewing the plan and warning confirmations.",
            )
        )
    if (
        plan.assay_type != "elisa_standard_curve"
        or plan.analysis_level != "measurement_rows"
        or plan.inverse_method != "four_parameter_logistic_inverse"
    ):
        issues.append(
            _issue(
                "UNSUPPORTED_INVERSE_PLAN",
                "Only a Phase 3B ELISA measurement-row inverse plan is supported.",
                "Generate a fresh Phase 3B inverse plan.",
            )
        )
    if (
        plan.intended_use != "research_only"
        or plan.research_only_acknowledged is not True
        or plan.validated_quantification_enabled is not False
        or plan.research_estimation_enabled is not True
    ):
        issues.append(
            _issue(
                "RESEARCH_SEMANTICS_INVALID",
                "The plan does not preserve the required research-only semantics.",
                "Use an unchanged plan with explicit research_only acknowledgement.",
            )
        )
    design_path, path_issues = _resolve_path(
        plan.inverse_design_path, allowed_root, "INVERSE_DESIGN", "inverse design"
    )
    issues.extend(path_issues)
    design: ELISAInverseDesign | None = None
    if design_path is not None:
        if plan.inverse_design_sha256 != sha256_file(design_path):
            issues.append(
                _issue(
                    "INVERSE_DESIGN_HASH_MISMATCH",
                    "The inverse design declaration changed.",
                    "Regenerate and reconfirm the plan.",
                )
            )
        design, design_issues = _load_design(design_path)
        issues.extend(design_issues)
    result_path, result_path_issues = _resolve_path(
        plan.inverse_curve_fit_result_path, allowed_root, "CURVE_RESULT", "curve result"
    )
    issues.extend(result_path_issues)
    curve_plan_path, curve_plan_issues = _resolve_path(
        plan.inverse_curve_plan_path, allowed_root, "CURVE_PLAN", "curve plan"
    )
    curve_preview_path, curve_preview_issues = _resolve_path(
        plan.inverse_curve_preview_path, allowed_root, "CURVE_PREVIEW", "standards preview"
    )
    curve_manifest_path, curve_manifest_issues = _resolve_path(
        plan.inverse_curve_manifest_path, allowed_root, "CURVE_MANIFEST", "curve manifest"
    )
    issues.extend(curve_plan_issues)
    issues.extend(curve_preview_issues)
    issues.extend(curve_manifest_issues)
    curve = (
        _curve_assets(
            result_path,
            plan_path=curve_plan_path,
            preview_path=curve_preview_path,
            manifest_path=curve_manifest_path,
            allowed_root=allowed_root,
        )
        if result_path is not None
        else _curve_assets(
            Path(allowed_root) / "missing-curve-result.json", allowed_root=allowed_root
        )
    )
    issues.extend(curve.issues)
    for actual, expected, code in (
        (curve.result_sha256, plan.inverse_curve_fit_result_sha256, "CURVE_RESULT_HASH_MISMATCH"),
        (curve.plan_sha256, plan.inverse_curve_plan_sha256, "CURVE_PLAN_HASH_MISMATCH"),
        (curve.preview_sha256, plan.inverse_curve_preview_sha256, "CURVE_PREVIEW_HASH_MISMATCH"),
        (curve.manifest_sha256, plan.inverse_curve_manifest_sha256, "CURVE_MANIFEST_HASH_MISMATCH"),
    ):
        if expected != actual:
            issues.append(
                _issue(
                    code,
                    "A bound Phase 3A artifact changed after plan generation.",
                    "Regenerate and reconfirm the inverse plan.",
                )
            )
    sample_path, sample_path_issues = _resolve_path(
        plan.inverse_sample_artifact_path, allowed_root, "SAMPLE_ARTIFACT", "sample import artifact"
    )
    issues.extend(sample_path_issues)
    sample_import: ImportResult | None = None
    sample_sha: str | None = None
    if sample_path is not None:
        sample_sha = sha256_file(sample_path)
        if plan.inverse_sample_artifact_sha256 != sample_sha:
            issues.append(
                _issue(
                    "SAMPLE_ARTIFACT_HASH_MISMATCH",
                    "The bound sample import artifact changed.",
                    "Regenerate and reconfirm the inverse plan.",
                )
            )
        sample_import, sample_issues = _load_import(sample_path)
        issues.extend(sample_issues)
        if sample_import is not None:
            if (
                sample_import.column_mapping != plan.inverse_sample_column_mapping
                or sample_import.parse_configuration != plan.inverse_sample_parse_configuration
            ):
                issues.append(
                    _issue(
                        "SAMPLE_CONFIGURATION_BINDING_MISMATCH",
                        "The sample mapping or parse configuration no longer matches the plan.",
                        "Regenerate and reconfirm the inverse plan.",
                    )
                )
            if sample_import.experiment_type != "elisa_standard_curve":
                issues.append(
                    _issue(
                        "UNSUPPORTED_SAMPLE_ASSAY",
                        "The sample artifact is not an ELISA import artifact.",
                        "Use an unchanged elisa_standard_curve import artifact.",
                    )
                )
            if not sample_import.analysis_ready or any(
                item.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
                for item in sample_import.validation_issues
            ):
                issues.append(
                    _issue(
                        "SAMPLE_IMPORT_QC_NOT_READY",
                        "The sample import artifact contains error or blocking QC issues.",
                        "Resolve import QC before inverse estimation.",
                    )
                )
            issues.extend(
                issue
                for issue in sample_import.validation_issues
                if issue.severity == IssueSeverity.WARNING
            )
    preview: SampleConcentrationPreview | None = None
    preview_path, preview_path_issues = _resolve_path(
        plan.inverse_preview_path, allowed_root, "INVERSE_PREVIEW", "inverse preview"
    )
    issues.extend(preview_path_issues)
    if preview_path is not None:
        if plan.inverse_preview_sha256 != sha256_file(preview_path):
            issues.append(
                _issue(
                    "INVERSE_PREVIEW_HASH_MISMATCH",
                    "The inverse preview changed after plan generation.",
                    "Regenerate and reconfirm the inverse plan.",
                )
            )
        try:
            preview = SampleConcentrationPreview.model_validate(_load_json(preview_path))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            issues.append(
                _issue(
                    "INVERSE_PREVIEW_INVALID",
                    f"The inverse preview is invalid: {type(exc).__name__}.",
                    "Use the unchanged preview generated with the plan.",
                )
            )
    if (
        design is not None
        and curve.result is not None
        and sample_import is not None
        and sample_sha is not None
    ):
        fresh, fresh_issues, _ = _build_sample_preview(
            curve.result,
            sample_import,
            design,
            curve_result_sha256=curve.result_sha256,
            sample_artifact_sha256=sample_sha,
        )
        row_level_codes = {
            "SAMPLE_RESPONSE_INVALID",
            "SAMPLE_INVERSE_NUMERICAL_FAILURE",
        }
        issues.extend(
            issue
            for issue in fresh_issues
            if issue.severity == IssueSeverity.WARNING or issue.code not in row_level_codes
        )
        if preview is None or preview.model_dump(mode="json") != fresh.model_dump(mode="json"):
            issues.append(
                _issue(
                    "INVERSE_PREVIEW_CONTENT_MISMATCH",
                    "The stored inverse preview does not match a fresh deterministic rebuild.",
                    "Regenerate and reconfirm the inverse plan.",
                )
            )
        required = _required_confirmation_codes(curve.result, fresh, sample_import)
        if plan.required_confirmations != required:
            issues.append(
                _issue(
                    "INVERSE_WARNING_SET_MISMATCH",
                    "The required warning set changed.",
                    "Regenerate and review the current inverse preview.",
                )
            )
        for code in required:
            if plan.warning_confirmations.get(code) is not True:
                issues.append(
                    _issue(
                        "REQUIRED_WARNING_NOT_CONFIRMED",
                        f"Warning {code} has not been explicitly confirmed.",
                        "Set the specific warning confirmation to true after review.",
                    )
                )
    if design is not None and (
        plan.sample_source_mode != design.sample_source_mode
        or plan.dilution_factor_source != design.dilution_factor_source
        or plan.dilution_factor_field != design.dilution_factor_field
        or plan.uniform_dilution_factor != design.uniform_dilution_factor
        or plan.allow_extrapolation is not False
        or plan.curve_context_compatibility_declared is not True
        or plan.curve_context_compatibility_rationale
        != design.curve_context_compatibility_rationale
        or plan.inverse_numeric_settings
        != {
            name: getattr(design, name)
            for name in (
                "response_tolerance",
                "asymptote_tolerance",
                "concentration_tolerance",
                "forward_check_tolerance",
                "log_overflow_threshold",
            )
        }
    ):
        issues.append(
            _issue(
                "INVERSE_DESIGN_BINDING_MISMATCH",
                "The plan no longer matches the explicit inverse design declaration.",
                "Regenerate and reconfirm the inverse plan.",
            )
        )
    if design is not None and sample_path is not None:
        expected_sample_path = (
            Path(curve.plan.input_artifact_path).resolve()
            if design.sample_source_mode == "same_import_artifact"
            and curve.plan is not None
            and curve.plan.input_artifact_path
            else Path(design.sample_artifact_path).resolve()
            if design.sample_artifact_path
            else None
        )
        if expected_sample_path is None or sample_path != expected_sample_path:
            issues.append(
                _issue(
                    "SAMPLE_SOURCE_BINDING_MISMATCH",
                    "The sample artifact path does not match the explicit source declaration.",
                    "Regenerate and reconfirm the inverse plan from the declared sample source.",
                )
            )
    if (
        sample_import is not None
        and plan.inverse_sample_source_sha256 != sample_import.input_file.sha256
    ):
        issues.append(
            _issue(
                "SAMPLE_SOURCE_HASH_MISMATCH",
                "The sample source SHA-256 does not match the import artifact.",
                "Regenerate and reconfirm the inverse plan.",
            )
        )
    return InverseExecutionPreflight(
        plan, design, curve, sample_import, preview, plan_sha, sample_sha, tuple(issues)
    )


def _failed_result(
    preflight: InverseExecutionPreflight, issues: list[ValidationIssue]
) -> SampleConcentrationsResult:
    curve = preflight.curve.result
    plan = preflight.plan
    return SampleConcentrationsResult(
        result_id=f"result-inverse-{uuid.uuid4().hex[:12]}",
        experiment_id=plan.experiment_id,
        plan_id=plan.plan_id,
        status="failed",
        direction=curve.direction if curve else "increasing",
        concentration_unit=curve.concentration_unit
        if curve
        else plan.declared_units.get("standard_concentration", "unspecified"),
        response_unit=curve.response_unit
        if curve
        else plan.declared_units.get("measurement", "unspecified"),
        issues=issues,
        total_sample_measurements=0,
        successful_estimates=0,
        below_standard_span_count=0,
        above_standard_span_count=0,
        outside_model_domain_count=0,
        near_asymptote_unstable_count=0,
        numerical_failure_count=0,
        curve_fit_result_sha256=preflight.curve.result_sha256,
        sample_artifact_sha256=preflight.sample_artifact_sha256,
        sample_source_sha256=preflight.sample_import.input_file.sha256
        if preflight.sample_import
        else None,
        confirmed_plan_sha256=preflight.plan_sha256,
        inverse_preview_sha256=preflight.plan.inverse_preview_sha256,
        known_limitations=INVERSE_LIMITATIONS,
    )


def compute_inverse_result(preflight: InverseExecutionPreflight) -> SampleConcentrationsResult:
    """Compute only after plan, curve, preview, and source revalidation."""
    blocking = [
        issue
        for issue in preflight.issues
        if issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
    ]
    if (
        preflight.design is None
        or preflight.sample_import is None
        or preflight.curve.result is None
        or preflight.preview is None
        or blocking
    ):
        return _failed_result(preflight, list(preflight.issues))
    curve = preflight.curve.result
    preview = preflight.preview
    records = list(preview.records)
    counts = {
        status: sum(item.status == status for item in records)
        for status in {
            "estimated_within_standard_span",
            "below_standard_span",
            "above_standard_span",
            "outside_model_domain",
            "near_asymptote_unstable",
            "numerical_failure",
        }
    }
    issues = list(preview.warnings) + [
        item
        for item in preview.blocking_reasons
        if item.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
    ]
    has_numerical_error = counts["numerical_failure"] > 0 or counts["outside_model_domain"] > 0
    status: InverseRunStatus = (
        "computed"
        if counts["estimated_within_standard_span"] == len(records) and not has_numerical_error
        else "partial"
        if records and not has_numerical_error
        else "partial"
        if records and counts["estimated_within_standard_span"] > 0
        else "failed"
    )
    return SampleConcentrationsResult(
        result_id=f"result-inverse-{uuid.uuid4().hex[:12]}",
        experiment_id=preflight.plan.experiment_id,
        plan_id=preflight.plan.plan_id,
        status=status,
        direction=curve.direction,
        concentration_unit=curve.concentration_unit,
        response_unit=curve.response_unit,
        observed_standard_concentration_span=curve.observed_standard_concentration_span,
        fitted_response_span=(records[0].curve_response_lower, records[0].curve_response_upper)
        if records
        and records[0].curve_response_lower is not None
        and records[0].curve_response_upper is not None
        else None,
        records=records,
        excluded_records=list(preview.excluded_records),
        total_sample_measurements=len(records),
        successful_estimates=counts["estimated_within_standard_span"],
        below_standard_span_count=counts["below_standard_span"],
        above_standard_span_count=counts["above_standard_span"],
        outside_model_domain_count=counts["outside_model_domain"],
        near_asymptote_unstable_count=counts["near_asymptote_unstable"],
        numerical_failure_count=counts["numerical_failure"],
        issues=issues,
        source_record_references={
            "sample_rows": [item.record_number for item in records],
            "excluded_rows": [item.record_number for item in preview.excluded_records],
        },
        curve_fit_result_sha256=preflight.curve.result_sha256,
        sample_artifact_sha256=preflight.sample_artifact_sha256,
        sample_source_sha256=preflight.sample_import.input_file.sha256,
        confirmed_plan_sha256=preflight.plan_sha256,
        inverse_preview_sha256=preflight.plan.inverse_preview_sha256,
        known_limitations=INVERSE_LIMITATIONS,
    )


def inverse_software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "scipy": scipy.__version__,
        "numpy": np.__version__,
        "statistics_implementation": "phase3b-4pl-inverse-v1",
    }


__all__ = [
    "INVERSE_LIMITATIONS",
    "InverseExecutionPreflight",
    "InversePlanBuild",
    "build_inverse_plan",
    "compute_inverse_result",
    "inverse_software_versions",
    "validate_inverse_execution_inputs",
]
