"""Restricted, deterministic Phase 3A ELISA standard-only 4PL fitting."""

from __future__ import annotations

import json
import math
import platform
import uuid
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.optimize import least_squares
from scipy.special import expit

from biolab_copilot.contracts import (
    AnalysisPlan,
    CurveFitPoint,
    CurveFitResult,
    CurveParameterBounds,
    CurveStartDiagnostic,
    ELISA4PLDesign,
    ImportResult,
    IssueSeverity,
    StandardLevelPreview,
    StandardRecordPreview,
    StandardsPreview,
    ValidationIssue,
)
from biolab_copilot.ingestion import sha256_file

FOUR_PL_LIMITATIONS = [
    (
        "Only standard rows participate in this Phase 3A fit; sample, blank, and control "
        "rows are retained but excluded."
    ),
    "The fit is a descriptive numerical 4PL calibration curve and is not a validated assay model.",
    (
        "curve_validated=false and quantification_enabled=false; no unknown-sample "
        "concentration is calculated."
    ),
    (
        "No blank subtraction, normalization, weighting, robust loss, point deletion, unit "
        "conversion, or 5PL fitting is performed."
    ),
    (
        "Observed standard concentration span is not an LLOQ, ULOQ, detection range, or "
        "validated quantification range."
    ),
]


@dataclass(frozen=True)
class CurvePlanBuild:
    plan: AnalysisPlan
    preview: StandardsPreview
    issues: tuple[ValidationIssue, ...]


@dataclass(frozen=True)
class CurveExecutionPreflight:
    plan: AnalysisPlan
    design: ELISA4PLDesign | None
    import_result: ImportResult | None
    preview: StandardsPreview | None
    plan_sha256: str
    issues: tuple[ValidationIssue, ...]


def _issue(
    code: str,
    message: str,
    suggested_action: str,
    *,
    severity: IssueSeverity = IssueSeverity.BLOCKING,
    location: str = "analysis_plan",
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        location=location,
        suggested_action=suggested_action,
        field=field,
        raw_value=None if raw_value is None else str(raw_value)[:200],
    )


def four_pl_predict(
    concentration: float,
    lower_asymptote: float,
    upper_asymptote: float,
    midpoint_concentration: float,
    slope_magnitude: float,
    direction: str,
) -> float:
    """Evaluate the declared 4PL using stable log/expit arithmetic."""

    if direction not in {"increasing", "decreasing"}:
        raise ValueError("direction must be increasing or decreasing")
    if not all(
        math.isfinite(value)
        for value in (
            concentration,
            lower_asymptote,
            upper_asymptote,
            midpoint_concentration,
            slope_magnitude,
        )
    ):
        raise ValueError("4PL inputs must be finite")
    if concentration < 0 or midpoint_concentration <= 0 or slope_magnitude <= 0:
        raise ValueError("4PL concentration must be nonnegative and C/B must be positive")
    if upper_asymptote <= lower_asymptote:
        raise ValueError("4PL requires upper_asymptote > lower_asymptote")
    if concentration == 0:
        return lower_asymptote if direction == "increasing" else upper_asymptote
    sign = 1.0 if direction == "increasing" else -1.0
    z = sign * slope_magnitude * (math.log(concentration) - math.log(midpoint_concentration))
    value = lower_asymptote + (upper_asymptote - lower_asymptote) * float(expit(z))
    if not math.isfinite(value):
        raise FloatingPointError("4PL prediction became non-finite")
    return value


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_import(path: Path) -> tuple[ImportResult | None, list[ValidationIssue]]:
    try:
        return ImportResult.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "INPUT_ARTIFACT_INVALID",
                f"The Phase 1 import artifact could not be validated: {type(exc).__name__}.",
                "Use an unchanged imported_data.json produced by the Phase 1 import CLI.",
                location=f"file={path.name}",
            )
        ]


def _load_design(path: Path) -> tuple[ELISA4PLDesign | None, list[ValidationIssue]]:
    try:
        return ELISA4PLDesign.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [
            _issue(
                "CURVE_DESIGN_INVALID",
                f"The explicit 4PL design declaration is invalid: {type(exc).__name__}.",
                "Provide all required Phase 3A design fields explicitly.",
                location=f"file={path.name}",
            )
        ]


def _source_location(record: Any) -> str:
    return next(iter(record.source_locations.values()), f"record={record.record_number}")


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:200]


def _parsed(record: Any, field: str) -> Any:
    return record.parsed_values.get(field)


def _raw(record: Any, field: str, column_mapping: dict[str, str]) -> Any:
    source_column = next(
        (source for source, canonical in column_mapping.items() if canonical == field), field
    )
    return record.raw_values.get(source_column)


def _unit_value(record: Any, field: str) -> str | None:
    value = _parsed(record, field)
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _record_issue(
    record: Any,
    code: str,
    message: str,
    suggested_action: str,
    *,
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=IssueSeverity.BLOCKING,
        message=message,
        location=_source_location(record),
        suggested_action=suggested_action,
        source_file=record.source_file,
        sheet_name=record.sheet_name,
        record_number=record.record_number,
        source_row_number=record.source_row_number,
        field=field,
        raw_value=_safe_text(raw_value),
    )


def _fit_bounds(
    levels: list[StandardLevelPreview],
) -> tuple[CurveParameterBounds, list[dict[str, float]]]:
    positive = [level.concentration for level in levels if level.concentration > 0]
    responses = [level.response_mean for level in levels]
    if not positive or not responses:
        return (
            CurveParameterBounds(
                lower_asymptote=(-1.0, 1.0),
                upper_asymptote=(0.0, 2.0),
                midpoint_concentration=(1e-6, 1.0),
                slope_magnitude=(1e-6, 20.0),
            ),
            [],
        )
    c_min, c_max = min(positive), max(positive)
    y_min, y_max = min(responses), max(responses)
    span = max(y_max - y_min, 1e-12)
    padding = max(10.0 * span, 0.1 * max(abs(y_min), abs(y_max), 1.0), 1.0)
    bounds = CurveParameterBounds(
        lower_asymptote=(y_min - padding, y_max + padding),
        upper_asymptote=(y_min - padding, y_max + padding),
        midpoint_concentration=(max(math.nextafter(0.0, 1.0), c_min / 1000.0), c_max * 1000.0),
        slope_magnitude=(1e-6, 100.0),
    )
    c_starts = [c_min, math.sqrt(c_min * c_max), c_max]
    l_starts = [y_min, y_min - 0.25 * span]
    u_starts = [y_max, y_max + 0.25 * span]
    b_starts = [0.5, 1.0, 2.0]
    starts: list[dict[str, float]] = []
    for lower in l_starts:
        for upper in u_starts:
            for midpoint in c_starts:
                for slope in b_starts:
                    if lower < upper:
                        starts.append(
                            {
                                "lower_asymptote": lower,
                                "upper_asymptote": upper,
                                "midpoint_concentration": midpoint,
                                "slope_magnitude": slope,
                            }
                        )
    return bounds, starts


def _preview_warning_codes(preview: StandardsPreview) -> list[str]:
    return sorted({issue.code for issue in preview.warnings})


def build_standards_preview(
    import_result: ImportResult,
    design: ELISA4PLDesign,
    *,
    input_artifact_sha256: str,
) -> tuple[StandardsPreview, list[ValidationIssue]]:
    """Build a fresh standard-only inclusion and aggregation preview."""

    warnings_found: list[ValidationIssue] = [
        issue
        for issue in import_result.validation_issues
        if issue.severity == IssueSeverity.WARNING
    ]
    blocking: list[ValidationIssue] = [
        issue
        for issue in import_result.validation_issues
        if issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
    ]
    records: list[StandardRecordPreview] = []
    candidates: list[tuple[Any, float, float, str | None]] = []
    duplicate_numbers = set(import_result.dataset_profile.duplicate_record_numbers)
    column_mapping = import_result.column_mapping
    for record in import_result.records:
        sample_type = _parsed(record, "sample_type")
        concentration = _parsed(record, "standard_concentration")
        response = _parsed(record, "measurement")
        repeat_id = (
            _parsed(record, design.standard_repeat_id_field)
            if design.standard_repeat_id_field is not None
            else None
        )
        included = sample_type == "standard"
        exclusion_reason = (
            None if included else f"sample_type={sample_type or 'missing'} is not standard"
        )
        if included:
            if record.record_number in duplicate_numbers:
                blocking.append(
                    _record_issue(
                        record,
                        "DUPLICATE_COMPLETE_RECORD_4PL",
                        "A duplicate complete standard record blocks fitting; it is retained.",
                        (
                            "Review the original record and regenerate the import artifact "
                            "after correction."
                        ),
                    )
                )
            if not isinstance(concentration, int | float) or not math.isfinite(concentration):
                blocking.append(
                    _record_issue(
                        record,
                        "STANDARD_CONCENTRATION_INVALID",
                        "A standard concentration is missing or non-finite.",
                        "Provide a finite standard concentration without imputation or conversion.",
                        field="standard_concentration",
                        raw_value=_raw(record, "standard_concentration", column_mapping),
                    )
                )
            elif concentration < 0:
                blocking.append(
                    _record_issue(
                        record,
                        "NEGATIVE_STANDARD_CONCENTRATION",
                        "A standard concentration is negative.",
                        (
                            "Use a nonnegative standard concentration and preserve the "
                            "original source."
                        ),
                        field="standard_concentration",
                        raw_value=concentration,
                    )
                )
            if not isinstance(response, int | float) or not math.isfinite(response):
                blocking.append(
                    _record_issue(
                        record,
                        "STANDARD_RESPONSE_INVALID",
                        "A standard response is missing or non-finite.",
                        "Provide a finite response value without imputation or deletion.",
                        field="measurement",
                        raw_value=_raw(record, "measurement", column_mapping),
                    )
                )
            for field, expected, label in (
                ("concentration_unit", design.concentration_unit, "concentration"),
                ("unit", design.response_unit, "response"),
                ("measurement_unit", design.response_unit, "response"),
            ):
                observed = _unit_value(record, field)
                if observed is not None and observed != expected:
                    blocking.append(
                        _record_issue(
                            record,
                            "UNIT_MISMATCH",
                            (
                                f"The {label} unit {observed!r} does not match the declared "
                                f"unit {expected!r}."
                            ),
                            (
                                "Correct the explicit unit declaration or source values; "
                                "no conversion is performed."
                            ),
                            field=field,
                            raw_value=observed,
                        )
                    )
            if design.standard_replicate_policy == "mean_by_concentration" and (
                repeat_id is None or str(repeat_id).strip() == ""
            ):
                    blocking.append(
                        _record_issue(
                            record,
                            "STANDARD_REPEAT_ID_REQUIRED",
                            "Mean-by-concentration requires an explicit repeat identifier.",
                            (
                                "Map and populate the declared repeat identifier for every "
                                "standard row."
                            ),
                            field=design.standard_repeat_id_field,
                        )
                    )
            if (
                isinstance(concentration, int | float)
                and math.isfinite(concentration)
                and concentration >= 0
                and isinstance(response, int | float)
                and math.isfinite(response)
            ):
                candidates.append(
                    (
                        record,
                        float(concentration),
                        float(response),
                        None if repeat_id is None else str(repeat_id),
                    )
                )
        records.append(
            StandardRecordPreview(
                record_number=record.record_number,
                source_location=_source_location(record),
                sample_id=_parsed(record, "sample_id"),
                sample_type=sample_type,
                raw_concentration=_safe_text(
                    _raw(record, "standard_concentration", column_mapping)
                ),
                parsed_concentration=concentration
                if isinstance(concentration, int | float)
                else None,
                raw_response=_safe_text(_raw(record, "measurement", column_mapping)),
                parsed_response=response if isinstance(response, int | float) else None,
                repeat_id=None if repeat_id is None else str(repeat_id),
                included=included,
                exclusion_reason=exclusion_reason,
            )
        )

    grouped: dict[float, list[tuple[Any, float, float, str | None]]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate[1], []).append(candidate)
    levels: list[StandardLevelPreview] = []
    for concentration in sorted(grouped):
        group = grouped[concentration]
        if design.standard_replicate_policy == "none" and len(group) != 1:
            blocking.append(
                _issue(
                    "STANDARD_REPLICATES_REQUIRE_EXPLICIT_POLICY",
                    "Multiple records share a concentration while standard_replicate_policy=none.",
                    (
                        "Declare mean_by_concentration with unique repeat identifiers or "
                        "provide one record per level."
                    ),
                    location=f"standard_concentration={concentration}",
                )
            )
        repeat_ids = [item[3] for item in group if item[3] is not None]
        if design.standard_replicate_policy == "mean_by_concentration" and len(repeat_ids) != len(
            set(repeat_ids)
        ):
            blocking.append(
                _issue(
                    "STANDARD_REPEAT_ID_NOT_UNIQUE",
                    "Repeat identifiers are not unique within a concentration level.",
                    "Provide one explicit repeat identifier per source record.",
                    location=f"standard_concentration={concentration}",
                )
            )
        values = [item[2] for item in group]
        mean = math.fsum(values) / len(values)
        sd = (
            None
            if len(values) < 2
            else math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1))
        )
        levels.append(
            StandardLevelPreview(
                concentration=concentration,
                n_measurements=len(values),
                response_mean=mean,
                response_sd=sd,
                source_record_numbers=[item[0].record_number for item in group],
                source_locations=[_source_location(item[0]) for item in group],
                repeat_ids=[item[3] for item in group if item[3] is not None],
            )
        )
    positive_levels = [level for level in levels if level.concentration > 0]
    if len(positive_levels) < 6:
        blocking.append(
            _issue(
                "INSUFFICIENT_POSITIVE_STANDARD_LEVELS",
                (
                    "At least 6 distinct positive standard concentrations are required; "
                    f"found {len(positive_levels)}."
                ),
                "Provide at least six distinct positive standard concentration levels.",
                location="standards_preview.fit_levels",
            )
        )
    if levels and len({level.response_mean for level in positive_levels}) <= 1:
        blocking.append(
            _issue(
                "CONSTANT_STANDARD_RESPONSE",
                (
                    "All positive standard response means are identical, so the 4PL is "
                    "not identifiable."
                ),
                "Review the source response values; no fallback model or point deletion is used.",
                location="standards_preview.fit_levels",
            )
        )
    if design.standard_replicate_policy == "mean_by_concentration" and levels:
        counts = {level.n_measurements for level in levels}
        if len(counts) > 1:
            warnings_found.append(
                _issue(
                    "UNEQUAL_STANDARD_REPLICATE_COUNTS",
                    (
                        "Standard concentration levels have different replicate counts; "
                        "levels remain equally weighted."
                    ),
                    "Review replicate coverage; no per-well weighting is applied.",
                    severity=IssueSeverity.WARNING,
                    location="standards_preview.fit_levels",
                )
            )
    if len(positive_levels) >= 2:
        means = [level.response_mean for level in positive_levels]
        increasing_bad = any(right < left for left, right in zip(means, means[1:], strict=False))
        decreasing_bad = any(right > left for left, right in zip(means, means[1:], strict=False))
        if (design.direction == "increasing" and increasing_bad) or (
            design.direction == "decreasing" and decreasing_bad
        ):
            warnings_found.append(
                _issue(
                    "NON_MONOTONIC_STANDARD_OBSERVATIONS",
                    "Observed standard means are not monotonic in the declared direction.",
                    (
                        "Review the source data and explicit direction before interpreting "
                        "the numerical fit."
                    ),
                    severity=IssueSeverity.WARNING,
                    location="standards_preview.fit_levels",
                )
            )
    preview = StandardsPreview(
        preview_id=f"preview-4pl-{input_artifact_sha256[:12]}",
        input_artifact_sha256=input_artifact_sha256,
        source_sha256=import_result.input_file.sha256,
        curve_context_description=design.curve_context_description,
        concentration_unit=design.concentration_unit,
        response_unit=design.response_unit,
        direction=design.direction,
        standard_replicate_policy=design.standard_replicate_policy,
        records=records,
        fit_levels=levels,
        warnings=warnings_found,
        blocking_reasons=blocking,
        preview_ready=not blocking,
    )
    return preview, [*warnings_found, *blocking]


def _design_plan_fields(design: ELISA4PLDesign) -> dict[str, Any]:
    return {
        "curve_direction": design.direction,
        "curve_context_declared": design.curve_context_declared,
        "curve_context_description": design.curve_context_description,
        "standard_replicate_policy": design.standard_replicate_policy,
        "standard_repeat_id_field": design.standard_repeat_id_field,
        "blank_policy": design.blank_policy,
        "weighting": design.weighting,
        "loss": design.loss,
        "optimizer": design.optimizer,
    }


def build_4pl_plan(
    input_artifact_path: Path,
    design_path: Path,
    preview_path: Path,
    *,
    generated_at: datetime | None = None,
) -> CurvePlanBuild:
    input_artifact_path = input_artifact_path.resolve()
    design_path = design_path.resolve()
    preview_path = preview_path.resolve()
    import_result, import_issues = _load_import(input_artifact_path)
    design, design_issues = _load_design(design_path)
    if import_result is None or design is None:
        raise ValueError("Cannot build a 4PL plan without a valid import and design declaration.")
    input_hash = sha256_file(input_artifact_path)
    design_hash = sha256_file(design_path)
    preview, preview_issues = build_standards_preview(
        import_result, design, input_artifact_sha256=input_hash
    )
    levels = preview.fit_levels
    bounds, all_starts = _fit_bounds(levels)
    starts = all_starts[: design.max_starts]
    plan = AnalysisPlan(
        plan_id=f"plan-4pl-{input_hash[:12]}-{design_hash[:12]}",
        experiment_id=import_result.dataset_profile.dataset_id,
        assay_type="elisa_standard_curve",
        objectives=["Fit one explicitly declared 4PL curve to standard rows only."],
        requested_outputs=[
            "analysis_plan",
            "standards_preview",
            "curve_fit_result",
            "analysis_issues",
            "run_manifest",
        ],
        configuration=import_result.parse_configuration,
        confirmed=False,
        input_artifact_path=str(input_artifact_path),
        input_artifact_sha256=input_hash,
        source_sha256=import_result.input_file.sha256,
        column_mapping=import_result.column_mapping,
        declared_units={
            "standard_concentration": design.concentration_unit,
            "measurement": design.response_unit,
        },
        group_field="sample_type",
        measurement_field="measurement",
        analysis_level="standard_curve_levels",
        statistics=[],
        required_confirmations=_preview_warning_codes(preview),
        warning_confirmations={code: False for code in _preview_warning_codes(preview)},
        generated_at=generated_at or datetime.now(UTC),
        optimizer_settings={
            "ftol": design.ftol,
            "xtol": design.xtol,
            "gtol": design.gtol,
            "max_nfev": design.max_nfev,
            "max_starts": design.max_starts,
        },
        parameter_bounds={
            "lower_asymptote": bounds.lower_asymptote,
            "upper_asymptote": bounds.upper_asymptote,
            "midpoint_concentration": bounds.midpoint_concentration,
            "slope_magnitude": bounds.slope_magnitude,
        },
        initial_starts=starts,
        diagnostic_thresholds={
            "boundary_proximity_threshold": design.boundary_proximity_threshold,
            "jacobian_condition_threshold": design.jacobian_condition_threshold,
        },
        standards_preview_path=str(preview_path),
        curve_design_path=str(design_path),
        curve_design_sha256=design_hash,
        included_standard_record_numbers=[
            record.record_number for record in preview.records if record.included
        ],
        excluded_record_reasons={
            str(record.record_number): record.exclusion_reason or "excluded"
            for record in preview.records
            if not record.included
        },
        **_design_plan_fields(design),
    )
    return CurvePlanBuild(
        plan=plan, preview=preview, issues=tuple([*import_issues, *design_issues, *preview_issues])
    )


def _invalid_plan() -> AnalysisPlan:
    return AnalysisPlan(
        plan_id="invalid-4pl-plan",
        experiment_id="invalid-4pl-plan",
        assay_type="elisa_standard_curve",
        objectives=["Invalid Phase 3A diagnostic placeholder"],
        analysis_level="standard_curve_levels",
        statistics=[],
    )


def _load_plan(path: Path) -> tuple[AnalysisPlan, list[ValidationIssue]]:
    try:
        return AnalysisPlan.model_validate(_load_json(path)), []
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return _invalid_plan(), [
            _issue(
                "ANALYSIS_PLAN_INVALID",
                f"The Phase 3A analysis plan is invalid: {type(exc).__name__}.",
                "Use an unchanged plan generated by generate-4pl-plan.",
                location=f"file={path.name}",
            )
        ]


def _resolve_bound_path(
    raw_path: str | None,
    *,
    allowed_root: Path,
    code: str,
    label: str,
    issues: list[ValidationIssue],
) -> Path | None:
    if raw_path is None:
        issues.append(
            _issue(
                f"{code}_MISSING",
                f"The plan does not bind a {label}.",
                f"Regenerate the plan with a project-local {label}.",
            )
        )
        return None
    path = Path(raw_path).resolve()
    try:
        path.relative_to(allowed_root.resolve())
    except ValueError:
        issues.append(
            _issue(
                f"{code}_OUTSIDE_PROJECT",
                f"The plan points to a {label} outside the project.",
                "Use a project-local bound artifact.",
                location=f"file={path}",
            )
        )
        return None
    if not path.is_file():
        issues.append(
            _issue(
                f"{code}_NOT_FOUND",
                f"The bound {label} is not available.",
                f"Restore the unchanged {label} or regenerate the plan.",
                location=f"file={path}",
            )
        )
        return None
    return path


def validate_4pl_execution_inputs(
    plan_path: Path,
    confirmed_plan_sha256: str,
    *,
    allowed_root: Path,
) -> CurveExecutionPreflight:
    plan_sha256 = sha256_file(plan_path)
    plan, issues = _load_plan(plan_path)
    design: ELISA4PLDesign | None = None
    import_result: ImportResult | None = None
    preview: StandardsPreview | None = None
    if confirmed_plan_sha256.lower() != plan_sha256:
        issues.append(
            _issue(
                "PLAN_HASH_MISMATCH",
                "The confirmed plan SHA-256 does not match the current plan file.",
                "Confirm the exact SHA-256 of the unchanged plan.",
            )
        )
    if not plan.confirmed:
        issues.append(
            _issue(
                "PLAN_NOT_CONFIRMED",
                "The 4PL plan is not explicitly confirmed.",
                (
                    "Set confirmed=true only after reviewing the plan and confirm its "
                    "resulting SHA-256."
                ),
                field="confirmed",
            )
        )
    if plan.assay_type != "elisa_standard_curve" or plan.analysis_level != "standard_curve_levels":
        issues.append(
            _issue(
                "UNSUPPORTED_4PL_PLAN",
                "Phase 3A accepts only an elisa_standard_curve standard_curve_levels plan.",
                "Generate a fresh Phase 3A 4PL plan.",
            )
        )
    try:
        CurveParameterBounds.model_validate(plan.parameter_bounds)
    except ValueError as exc:
        issues.append(
            _issue(
                "PARAMETER_BOUNDS_INVALID",
                f"The plan numerical parameter bounds are invalid: {exc}.",
                (
                    "Regenerate the plan; do not hand-edit numerical constraints into an "
                    "invalid state."
                ),
                field="parameter_bounds",
            )
        )
    if not plan.initial_starts:
        issues.append(
            _issue(
                "INITIAL_STARTS_MISSING",
                "The plan does not contain deterministic initial starts.",
                "Regenerate the plan with its complete numerical configuration.",
                field="initial_starts",
            )
        )
    design_path = _resolve_bound_path(
        plan.curve_design_path,
        allowed_root=allowed_root,
        code="CURVE_DESIGN",
        label="4PL design declaration",
        issues=issues,
    )
    if design_path is not None:
        actual = sha256_file(design_path)
        if plan.curve_design_sha256 != actual:
            issues.append(
                _issue(
                    "CURVE_DESIGN_HASH_MISMATCH",
                    "The bound 4PL design declaration changed.",
                    "Regenerate and reconfirm the plan.",
                    field="curve_design_sha256",
                )
            )
        design, design_issues = _load_design(design_path)
        issues.extend(design_issues)
        if design is not None and any(
            getattr(plan, name) != value for name, value in _design_plan_fields(design).items()
        ):
            issues.append(
                _issue(
                    "CURVE_DESIGN_BINDING_MISMATCH",
                    "The design declaration no longer matches the plan.",
                    "Regenerate the plan from the unchanged design declaration.",
                )
            )
    input_path = _resolve_bound_path(
        plan.input_artifact_path,
        allowed_root=allowed_root,
        code="INPUT_ARTIFACT",
        label="Phase 1 import artifact",
        issues=issues,
    )
    if input_path is not None:
        if plan.input_artifact_sha256 != sha256_file(input_path):
            issues.append(
                _issue(
                    "INPUT_ARTIFACT_HASH_MISMATCH",
                    "The bound import artifact changed.",
                    "Regenerate and reconfirm the plan.",
                )
            )
        import_result, import_issues = _load_import(input_path)
        issues.extend(import_issues)
    preview_path = _resolve_bound_path(
        plan.standards_preview_path,
        allowed_root=allowed_root,
        code="STANDARDS_PREVIEW",
        label="standards preview",
        issues=issues,
    )
    if preview_path is not None:
        if plan.standards_preview_sha256 != sha256_file(preview_path):
            issues.append(
                _issue(
                    "STANDARDS_PREVIEW_HASH_MISMATCH",
                    "The bound standards preview changed.",
                    "Regenerate and reconfirm the plan.",
                )
            )
        try:
            preview = StandardsPreview.model_validate(_load_json(preview_path))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            issues.append(
                _issue(
                    "STANDARDS_PREVIEW_INVALID",
                    f"The standards preview is invalid: {type(exc).__name__}.",
                    "Use the unchanged preview generated with the plan.",
                )
            )
    if import_result is not None:
        if import_result.experiment_type != "elisa_standard_curve":
            issues.append(
                _issue(
                    "UNSUPPORTED_INPUT_ASSAY",
                    "Phase 3A accepts only elisa_standard_curve input.",
                    "Use an ELISA standard-curve import artifact.",
                )
            )
        if not import_result.analysis_ready or any(
            issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
            for issue in import_result.validation_issues
        ):
            issues.append(
                _issue(
                    "IMPORT_QC_NOT_READY",
                    "The import artifact contains error/blocking QC issues.",
                    "Resolve import QC issues; no erroneous row is silently bypassed.",
                )
            )
        if plan.source_sha256 != import_result.input_file.sha256:
            issues.append(
                _issue(
                    "SOURCE_HASH_BINDING_MISMATCH",
                    "The plan source hash does not match the import artifact.",
                    "Regenerate the plan.",
                )
            )
        if (
            plan.column_mapping != import_result.column_mapping
            or plan.configuration != import_result.parse_configuration
        ):
            issues.append(
                _issue(
                    "IMPORT_CONFIGURATION_BINDING_MISMATCH",
                    (
                        "The plan mapping or parsing configuration no longer matches the "
                        "import artifact."
                    ),
                    "Regenerate the plan from the unchanged import artifact.",
                )
            )
    if preview is not None and design is not None and import_result is not None:
        fresh_preview, fresh_issues = build_standards_preview(
            import_result, design, input_artifact_sha256=plan.input_artifact_sha256 or ""
        )
        issues.extend(fresh_preview.warnings)
        issues.extend(
            [
                issue
                for issue in fresh_issues
                if issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}
            ]
        )
        if preview.model_dump(mode="json") != fresh_preview.model_dump(mode="json"):
            issues.append(
                _issue(
                    "STANDARDS_PREVIEW_CONTENT_MISMATCH",
                    "The preview does not match a fresh deterministic rebuild.",
                    "Regenerate the preview and reconfirm the plan.",
                )
            )
        current_codes = _preview_warning_codes(fresh_preview)
        if plan.required_confirmations != current_codes:
            issues.append(
                _issue(
                    "PLAN_WARNING_SET_MISMATCH",
                    "The plan warning set no longer matches the fresh preview.",
                    "Regenerate and review the current warnings.",
                )
            )
        for code in current_codes:
            if plan.warning_confirmations.get(code) is not True:
                issues.append(
                    _issue(
                        "REQUIRED_WARNING_NOT_CONFIRMED",
                        f"Warning {code} has not been explicitly confirmed.",
                        "Set its warning_confirmations value to true after review.",
                    )
                )
        if not fresh_preview.preview_ready:
            issues.append(
                _issue(
                    "STANDARDS_PREVIEW_BLOCKED",
                    "The standards preview contains blocking reasons.",
                    "Resolve the standard data/design issues before fitting.",
                )
            )
    return CurveExecutionPreflight(plan, design, import_result, preview, plan_sha256, tuple(issues))


def _failed_result(
    preflight: CurveExecutionPreflight, issues: list[ValidationIssue]
) -> CurveFitResult:
    plan = preflight.plan
    preview = preflight.preview
    return CurveFitResult(
        result_id=f"result-{uuid.uuid4().hex[:12]}",
        experiment_id=plan.experiment_id,
        plan_id=plan.plan_id,
        status="failed",
        direction=plan.curve_direction or "increasing",
        concentration_unit=plan.declared_units.get("standard_concentration", "unspecified"),
        response_unit=plan.declared_units.get("measurement", "unspecified"),
        n_fit_levels=len(preview.fit_levels) if preview else 0,
        n_raw_standard_measurements=sum(level.n_measurements for level in preview.fit_levels)
        if preview
        else 0,
        issues=issues,
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=preflight.import_result.input_file.sha256
        if preflight.import_result
        else plan.source_sha256,
        confirmed_plan_sha256=preflight.plan_sha256,
        standards_preview_sha256=plan.standards_preview_sha256,
        known_limitations=FOUR_PL_LIMITATIONS,
    )


def _internal_start(start: dict[str, float]) -> np.ndarray:
    delta = start["upper_asymptote"] - start["lower_asymptote"]
    return np.asarray(
        [
            start["lower_asymptote"],
            math.log(delta),
            math.log(start["midpoint_concentration"]),
            math.log(start["slope_magnitude"]),
        ],
        dtype=np.float64,
    )


def _semantic_parameters(theta: np.ndarray) -> tuple[float, float, float, float]:
    lower = float(theta[0])
    delta = math.exp(float(theta[1]))
    midpoint = math.exp(float(theta[2]))
    slope = math.exp(float(theta[3]))
    return lower, lower + delta, midpoint, slope


def _fit_one_start(
    start_index: int,
    start: dict[str, float],
    x: np.ndarray,
    y: np.ndarray,
    direction: str,
    bounds: CurveParameterBounds,
    settings: dict[str, float | int],
) -> tuple[CurveStartDiagnostic, Any | None]:
    diagnostics: list[str] = []
    try:
        x0 = _internal_start(start)
        internal_lower = np.asarray(
            [
                bounds.lower_asymptote[0],
                math.log(max(bounds.upper_asymptote[0] - bounds.lower_asymptote[0], 1e-12)),
                math.log(bounds.midpoint_concentration[0]),
                math.log(bounds.slope_magnitude[0]),
            ],
            dtype=np.float64,
        )
        internal_upper = np.asarray(
            [
                bounds.lower_asymptote[1],
                math.log(bounds.upper_asymptote[1] - bounds.lower_asymptote[0]),
                math.log(bounds.midpoint_concentration[1]),
                math.log(bounds.slope_magnitude[1]),
            ],
            dtype=np.float64,
        )
        if np.any(x0 <= internal_lower) or np.any(x0 >= internal_upper):
            raise ValueError("deterministic initial point lies outside optimizer bounds")

        def residual(theta: np.ndarray) -> np.ndarray:
            lower, upper, midpoint, slope = _semantic_parameters(theta)
            return np.asarray(
                [
                    four_pl_predict(float(value), lower, upper, midpoint, slope, direction)
                    for value in x
                ]
                - y,
                dtype=np.float64,
            )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fit = least_squares(
                residual,
                x0,
                bounds=(internal_lower, internal_upper),
                loss="linear",
                x_scale="jac",
                ftol=float(settings["ftol"]),
                xtol=float(settings["xtol"]),
                gtol=float(settings["gtol"]),
                max_nfev=int(settings["max_nfev"]),
            )
            diagnostics = [f"{item.category.__name__}: {item.message}" for item in caught]
        parameters = _semantic_parameters(np.asarray(fit.x, dtype=np.float64))
        sse = float(np.dot(fit.fun, fit.fun))
        finite = all(math.isfinite(value) for value in (*parameters, sse)) and np.all(
            np.isfinite(fit.fun)
        )
        valid_bounds = (
            bounds.lower_asymptote[0] <= parameters[0] <= bounds.lower_asymptote[1]
            and bounds.upper_asymptote[0] <= parameters[1] <= bounds.upper_asymptote[1]
            and bounds.midpoint_concentration[0]
            <= parameters[2]
            <= bounds.midpoint_concentration[1]
            and bounds.slope_magnitude[0] <= parameters[3] <= bounds.slope_magnitude[1]
        )
        success = bool(fit.success and finite and valid_bounds)
        failure = (
            None if success else "optimizer did not produce a finite in-bound converged candidate"
        )
        diagnostic = CurveStartDiagnostic(
            start_index=start_index,
            initial_parameters=start,
            success=success,
            objective_sse=sse if finite else None,
            nfev=int(fit.nfev),
            termination_status=int(fit.status),
            termination_reason=str(fit.message),
            failure_reason=failure,
            warnings=diagnostics,
        )
        return diagnostic, fit
    except (FloatingPointError, OverflowError, ValueError, RuntimeError) as exc:
        return CurveStartDiagnostic(
            start_index=start_index,
            initial_parameters=start,
            success=False,
            failure_reason=f"{type(exc).__name__}: {exc}",
            warnings=diagnostics,
        ), None


def compute_4pl_fit(preflight: CurveExecutionPreflight) -> CurveFitResult:
    """Execute a revalidated, explicitly confirmed standard-only 4PL fit."""

    issues = list(preflight.issues)
    if (
        preflight.import_result is None
        or preflight.preview is None
        or preflight.design is None
        or any(issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING} for issue in issues)
    ):
        return _failed_result(preflight, issues)
    preview = preflight.preview
    plan = preflight.plan
    levels = preview.fit_levels
    bounds = CurveParameterBounds.model_validate(plan.parameter_bounds)
    starts = plan.initial_starts
    x = np.asarray([level.concentration for level in levels], dtype=np.float64)
    y = np.asarray([level.response_mean for level in levels], dtype=np.float64)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        issues.append(
            _issue(
                "NON_FINITE_FIT_INPUT",
                "A non-finite concentration or response reached the fit boundary.",
                "Resolve the source value without imputation.",
            )
        )
        return _failed_result(preflight, issues)
    positive = x[x > 0]
    if positive.size < 6:
        issues.append(
            _issue(
                "INSUFFICIENT_POSITIVE_STANDARD_LEVELS",
                "At least six positive fit levels are required.",
                "Provide six distinct positive concentrations.",
            )
        )
        return _failed_result(preflight, issues)
    if len(set(float(value) for value in y[x > 0])) <= 1:
        issues.append(
            _issue(
                "CONSTANT_STANDARD_RESPONSE",
                "Constant standard responses cannot identify a 4PL.",
                "Review the source response values.",
            )
        )
        return _failed_result(preflight, issues)
    settings = plan.optimizer_settings
    diagnostics: list[CurveStartDiagnostic] = []
    candidates: list[tuple[float, int, Any]] = []
    for index, start in enumerate(starts):
        diagnostic, fit = _fit_one_start(
            index, start, x, y, plan.curve_direction or "increasing", bounds, settings
        )
        diagnostics.append(diagnostic)
        if diagnostic.success and fit is not None and diagnostic.objective_sse is not None:
            candidates.append((diagnostic.objective_sse, index, fit))
        for warning_message in diagnostic.warnings:
            issues.append(
                _issue(
                    "OPTIMIZER_NUMERICAL_WARNING",
                    f"Optimizer start {index} emitted a numerical warning: {warning_message}",
                    "Review the start diagnostic and numerical scale before interpretation.",
                    severity=IssueSeverity.WARNING,
                    location=f"curve_fit.start[{index}]",
                )
            )
    if not candidates:
        issues.append(
            _issue(
                "OPTIMIZATION_NO_CONVERGED_CANDIDATE",
                "No deterministic 4PL start produced a finite in-bound converged candidate.",
                (
                    "Review the explicit direction, numerical bounds, response scale, and "
                    "data without switching models or deleting points."
                ),
            )
        )
        return _failed_result(preflight, [*issues]).model_copy(
            update={
                "start_diagnostics": diagnostics,
                "convergence_status": "failed",
                "termination_reason": "all deterministic starts failed",
            }
        )
    _, selected_index, selected_fit = min(candidates, key=lambda item: (item[0], item[1]))
    lower, upper, midpoint, slope = _semantic_parameters(
        np.asarray(selected_fit.x, dtype=np.float64)
    )
    predictions = np.asarray(
        [
            four_pl_predict(
                float(value), lower, upper, midpoint, slope, plan.curve_direction or "increasing"
            )
            for value in x
        ],
        dtype=np.float64,
    )
    residuals = y - predictions
    sse = float(np.dot(residuals, residuals))
    rmse = math.sqrt(sse / len(levels))
    y_mean = float(np.mean(y))
    sst = float(np.dot(y - y_mean, y - y_mean))
    r_squared = None if sst == 0 else 1.0 - sse / sst
    if r_squared is None:
        r_squared_reason = "The fitted-level response denominator is zero."
    else:
        r_squared_reason = (
            "Descriptive R² calculated only on the selected fitted concentration levels."
        )
    if not all(
        math.isfinite(value)
        for value in (lower, upper, midpoint, slope, sse, rmse, *predictions, *residuals)
    ):
        issues.append(
            _issue(
                "NON_FINITE_FIT_RESULT",
                "The converged candidate produced a non-finite result.",
                "Do not use this result; review the numeric scale and source data.",
            )
        )
        return _failed_result(preflight, issues)
    jacobian = np.asarray(selected_fit.jac, dtype=np.float64)
    rank = int(np.linalg.matrix_rank(jacobian))
    try:
        condition = float(np.linalg.cond(jacobian))
    except np.linalg.LinAlgError:
        condition = math.inf
    if rank < 4:
        issues.append(
            _issue(
                "JACOBIAN_RANK_DEFICIENT",
                (
                    "The fitted Jacobian is rank deficient; parameter identifiability is "
                    "numerically limited."
                ),
                "Treat the candidate as a numerical diagnostic, not a validated curve.",
                severity=IssueSeverity.WARNING,
                location="curve_fit.jacobian",
            )
        )
    if not math.isfinite(condition) or condition >= plan.diagnostic_thresholds.get(
        "jacobian_condition_threshold", 1e10
    ):
        issues.append(
            _issue(
                "JACOBIAN_ILL_CONDITIONED",
                "The fitted Jacobian is ill-conditioned by the configured numerical threshold.",
                "Review the concentration span and response pattern before interpretation.",
                severity=IssueSeverity.WARNING,
                location="curve_fit.jacobian",
            )
        )
    threshold = plan.diagnostic_thresholds.get("boundary_proximity_threshold", 1e-6)
    semantic = {
        "lower_asymptote": lower,
        "upper_asymptote": upper,
        "midpoint_concentration": midpoint,
        "slope_magnitude": slope,
    }
    boundary_flags: dict[str, bool] = {}
    for name, value in semantic.items():
        low, high = plan.parameter_bounds[name]
        boundary_flags[name] = (
            min(abs(value - low), abs(high - value)) / max(high - low, 1.0) <= threshold
        )
        if boundary_flags[name]:
            issues.append(
                _issue(
                    "PARAMETER_NEAR_BOUNDARY",
                    f"{name} is near a configured numerical bound.",
                    "Review the numerical warning; the bound is not a biological fact.",
                    severity=IssueSeverity.WARNING,
                    location=f"curve_fit.parameters.{name}",
                )
            )
    c_min, c_max = min(float(value) for value in positive), max(float(value) for value in positive)
    if not c_min <= midpoint <= c_max:
        issues.append(
            _issue(
                "MIDPOINT_OUTSIDE_OBSERVED_SPAN",
                "The fitted midpoint is outside the observed positive standard concentration span.",
                "Treat the extrapolative midpoint as a numerical diagnostic only.",
                severity=IssueSeverity.WARNING,
                location="curve_fit.midpoint_concentration",
            )
        )
    fit_points = [
        CurveFitPoint(
            concentration=level.concentration,
            observed=level.response_mean,
            predicted=float(prediction),
            residual=float(residual),
            n_measurements=level.n_measurements,
            source_record_numbers=level.source_record_numbers,
        )
        for level, prediction, residual in zip(levels, predictions, residuals, strict=False)
    ]
    return CurveFitResult(
        result_id=f"result-{uuid.uuid4().hex[:12]}",
        experiment_id=preflight.import_result.dataset_profile.dataset_id,
        plan_id=plan.plan_id,
        status="computed",
        direction=plan.curve_direction or "increasing",
        concentration_unit=plan.declared_units.get("standard_concentration", "unspecified"),
        response_unit=plan.declared_units.get("measurement", "unspecified"),
        lower_asymptote=lower,
        upper_asymptote=upper,
        midpoint_concentration=midpoint,
        slope_magnitude=slope,
        parameter_semantics={
            "lower_asymptote": "L; lower asymptote in response units",
            "upper_asymptote": "U; upper asymptote in response units, U>L",
            "midpoint_concentration": (
                "C; midpoint concentration in declared concentration units, C>0; not a "
                "validated EC50"
            ),
            "slope_magnitude": "B; positive slope magnitude, B>0",
        },
        fit_points=fit_points,
        n_fit_levels=len(levels),
        n_raw_standard_measurements=sum(level.n_measurements for level in levels),
        observed_standard_concentration_span=(c_min, c_max),
        midpoint_within_observed_positive_span=c_min <= midpoint <= c_max,
        sse=sse,
        rmse=rmse,
        r_squared=r_squared,
        r_squared_reason=r_squared_reason,
        convergence_status="converged_candidate_selected",
        termination_reason=str(selected_fit.message),
        selected_start_index=selected_index,
        start_diagnostics=diagnostics,
        parameter_boundary_flags=boundary_flags,
        jacobian_rank=rank,
        jacobian_condition_number=condition if math.isfinite(condition) else None,
        jacobian_scale_description=(
            "Condition number is computed on the optimizer Jacobian in transformed "
            "parameters [L, log(U-L), log(C), log(B)]."
        ),
        issues=issues,
        source_record_references={
            "fit_levels": [record for level in levels for record in level.source_record_numbers],
            "excluded_records": [
                record.record_number for record in preview.records if not record.included
            ],
        },
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=preflight.import_result.input_file.sha256,
        confirmed_plan_sha256=preflight.plan_sha256,
        standards_preview_sha256=plan.standards_preview_sha256,
        known_limitations=FOUR_PL_LIMITATIONS,
    )


def four_pl_software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "scipy": scipy.__version__,
        "numpy": np.__version__,
    }


__all__ = [
    "FOUR_PL_LIMITATIONS",
    "CurveExecutionPreflight",
    "CurvePlanBuild",
    "build_4pl_plan",
    "build_standards_preview",
    "compute_4pl_fit",
    "four_pl_predict",
    "four_pl_software_versions",
    "validate_4pl_execution_inputs",
]
