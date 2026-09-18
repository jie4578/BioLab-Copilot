"""Deterministic measurement-row descriptive statistics for Phase 2A."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from typing import Any

from biolab_copilot.contracts import (
    AnalysisPlan,
    AnalysisResult,
    GroupDescriptiveStats,
    ImportResult,
    IssueSeverity,
    ValidationIssue,
)
from biolab_copilot.statistics.plans import PHASE2A_STATISTICS

STATISTICAL_LIMITATIONS = [
    "Statistics describe measurement_rows, not independent biological samples.",
    "independent_biological_n is not determined in Phase 2A and remains null.",
    "Technical repeats, unknown repeats, and duplicate records are not aggregated or removed.",
    (
        "No inferential test, p-value, effect size, confidence interval, CV, imputation, "
        "or transformation is produced."
    ),
]


def _issue(
    code: str,
    message: str,
    suggested_action: str,
    *,
    location: str,
    record_number: int | None = None,
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=IssueSeverity.BLOCKING,
        message=message,
        location=location,
        suggested_action=suggested_action,
        record_number=record_number,
        field=field,
        raw_value=None if raw_value is None else str(raw_value)[:200],
    )


def _failed_result(
    import_result: ImportResult,
    plan: AnalysisPlan,
    plan_sha256: str,
    issues: list[ValidationIssue],
    source_record_references: dict[str, list[int]],
) -> AnalysisResult:
    return AnalysisResult(
        result_id=f"result-{uuid.uuid4().hex[:12]}",
        experiment_id=import_result.dataset_profile.dataset_id,
        plan_id=plan.plan_id,
        status="failed",
        issues=[*import_result.validation_issues, *issues],
        analysis_level="measurement_rows",
        declared_units=plan.declared_units,
        source_record_references=source_record_references,
        independent_biological_n=None,
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=import_result.input_file.sha256,
        confirmed_plan_sha256=plan_sha256,
        statistical_limitations=STATISTICAL_LIMITATIONS,
    )


def _finite_sum(
    values: list[float], *, location: str
) -> tuple[float | None, ValidationIssue | None]:
    try:
        total = math.fsum(values)
    except OverflowError:
        return None, _issue(
            "NON_FINITE_STATISTIC",
            "The deterministic sum overflowed while computing a descriptive statistic.",
            "Review finite source values and rerun without changing the source data.",
            location=location,
        )
    if not math.isfinite(total):
        return None, _issue(
            "NON_FINITE_STATISTIC",
            "A descriptive statistic became non-finite during deterministic computation.",
            "Review finite source values and rerun without changing the source data.",
            location=location,
        )
    return total, None


def _group_statistics(
    group: str,
    record_values: list[tuple[int, float]],
) -> tuple[GroupDescriptiveStats | None, ValidationIssue | None]:
    location = f"group={group!r}"
    values = [value for _, value in record_values]
    n_measurements = len(values)
    total, issue = _finite_sum(values, location=location)
    if issue is not None or total is None:
        return None, issue
    mean = total / n_measurements
    if not math.isfinite(mean):
        return None, _issue(
            "NON_FINITE_STATISTIC",
            "The group mean became non-finite during deterministic computation.",
            "Review finite source values and rerun without changing the source data.",
            location=location,
        )

    ordered = sorted(values)
    if n_measurements % 2:
        median = ordered[n_measurements // 2]
    else:
        median_total, issue = _finite_sum(
            [ordered[n_measurements // 2 - 1], ordered[n_measurements // 2]],
            location=location,
        )
        if issue is not None or median_total is None:
            return None, issue
        median = median_total / 2
    if not math.isfinite(median):
        return None, _issue(
            "NON_FINITE_STATISTIC",
            "The group median became non-finite during deterministic computation.",
            "Review finite source values and rerun without changing the source data.",
            location=location,
        )

    sample_sd: float | None = None
    sample_sd_reason: str | None = None
    if n_measurements == 1:
        sample_sd_reason = "sample_sd requires at least two measurement rows (ddof=1)."
    else:
        squared_deviations: list[float] = []
        for value in values:
            deviation = value - mean
            squared = deviation * deviation
            if not math.isfinite(squared):
                return None, _issue(
                    "NON_FINITE_STATISTIC",
                    "A squared deviation became non-finite while computing sample_sd.",
                    "Review finite source values and rerun without changing the source data.",
                    location=location,
                )
            squared_deviations.append(squared)
        sum_squared, issue = _finite_sum(squared_deviations, location=location)
        if issue is not None or sum_squared is None:
            return None, issue
        variance = sum_squared / (n_measurements - 1)
        if not math.isfinite(variance):
            return None, _issue(
                "NON_FINITE_STATISTIC",
                "The sample variance became non-finite while computing sample_sd.",
                "Review finite source values and rerun without changing the source data.",
                location=location,
            )
        sample_sd = math.sqrt(variance)
        if not math.isfinite(sample_sd):
            return None, _issue(
                "NON_FINITE_STATISTIC",
                "The sample_sd became non-finite during deterministic computation.",
                "Review finite source values and rerun without changing the source data.",
                location=location,
            )

    return (
        GroupDescriptiveStats(
            group=group,
            n_measurements=n_measurements,
            mean=mean,
            median=median,
            min=ordered[0],
            max=ordered[-1],
            sample_sd=sample_sd,
            sample_sd_reason=sample_sd_reason,
            source_record_numbers=[record_number for record_number, _ in record_values],
        ),
        None,
    )


def compute_grouped_descriptive(
    import_result: ImportResult,
    plan: AnalysisPlan,
    confirmed_plan_sha256: str,
) -> AnalysisResult:
    """Compute the fixed Phase 2A descriptive set without changing source records."""

    precondition_issues: list[ValidationIssue] = []
    if not plan.confirmed:
        precondition_issues.append(
            _issue(
                "PLAN_NOT_CONFIRMED",
                "The analysis plan is not explicitly confirmed.",
                "Confirm the plan file and its SHA-256 before execution.",
                location="analysis_plan",
            )
        )
    if plan.assay_type != "generic_grouped":
        precondition_issues.append(
            _issue(
                "UNSUPPORTED_PHASE2A_ASSAY",
                "Phase 2A descriptive statistics support only generic_grouped.",
                "Use a confirmed generic_grouped plan.",
                location="analysis_plan",
                field="assay_type",
            )
        )
    if plan.analysis_level != "measurement_rows" or list(plan.statistics) != PHASE2A_STATISTICS:
        precondition_issues.append(
            _issue(
                "UNSUPPORTED_ANALYSIS_LEVEL_OR_STATISTICS",
                "The plan is not the fixed Phase 2A measurement-row descriptive plan.",
                (
                    "Use the generated Phase 2A plan without changing its analysis level or "
                    "statistic set."
                ),
                location="analysis_plan",
            )
        )
    for code in plan.required_confirmations:
        if plan.warning_confirmations.get(code) is not True:
            precondition_issues.append(
                _issue(
                    "REQUIRED_WARNING_NOT_CONFIRMED",
                    f"Warning {code} has not received explicit confirmation.",
                    "Confirm each required warning in the plan before execution.",
                    location="analysis_plan",
                    field=f"warning_confirmations.{code}",
                )
            )
    if precondition_issues:
        return _failed_result(
            import_result,
            plan,
            confirmed_plan_sha256,
            precondition_issues,
            {},
        )

    grouped: dict[str, list[tuple[int, float]]] = defaultdict(list)
    issues: list[ValidationIssue] = []
    for record in import_result.records:
        group_value = record.parsed_values.get(plan.group_field)
        measurement_value = record.parsed_values.get(plan.measurement_field)
        if not isinstance(group_value, str) or not group_value.strip():
            issues.append(
                _issue(
                    "INVALID_ANALYSIS_GROUP",
                    "A measurement row has no valid non-empty group value.",
                    "Resolve the Phase 1 group-field QC issue and regenerate the import artifact.",
                    location=record.source_locations.get(plan.group_field, "analysis_record"),
                    record_number=record.record_number,
                    field=plan.group_field,
                    raw_value=group_value,
                )
            )
            continue
        if (
            isinstance(measurement_value, bool)
            or not isinstance(measurement_value, int | float)
            or not math.isfinite(float(measurement_value))
        ):
            issues.append(
                _issue(
                    "INVALID_ANALYSIS_MEASUREMENT",
                    "A measurement row does not contain a finite numeric value.",
                    (
                        "Resolve the Phase 1 measurement-field QC issue and regenerate the "
                        "import artifact."
                    ),
                    location=record.source_locations.get(
                        plan.measurement_field, "analysis_record"
                    ),
                    record_number=record.record_number,
                    field=plan.measurement_field,
                    raw_value=measurement_value,
                )
            )
            continue
        grouped[group_value].append((record.record_number, float(measurement_value)))

    source_references = {
        group: [record_number for record_number, _ in grouped[group]]
        for group in sorted(grouped)
    }
    if issues:
        return _failed_result(
            import_result, plan, confirmed_plan_sha256, issues, source_references
        )
    if not grouped:
        issues.append(
            _issue(
                "NO_MEASUREMENT_ROWS",
                "No valid measurement rows are available for descriptive statistics.",
                "Provide a non-empty generic_grouped import with finite measurements.",
                location="analysis_result",
            )
        )
        return _failed_result(
            import_result, plan, confirmed_plan_sha256, issues, source_references
        )

    group_statistics: list[GroupDescriptiveStats] = []
    for group in sorted(grouped):
        group_result, issue = _group_statistics(group, grouped[group])
        if issue is not None or group_result is None:
            issues.append(issue or _issue(
                "STATISTIC_COMPUTATION_FAILED",
                "A group descriptive statistic could not be computed.",
                "Review the diagnostic and rerun after resolving the source or numeric issue.",
                location=f"group={group!r}",
            ))
        else:
            group_statistics.append(group_result)
    if issues:
        return _failed_result(
            import_result, plan, confirmed_plan_sha256, issues, source_references
        )

    return AnalysisResult(
        result_id=f"result-{uuid.uuid4().hex[:12]}",
        experiment_id=import_result.dataset_profile.dataset_id,
        plan_id=plan.plan_id,
        status="computed",
        issues=list(import_result.validation_issues),
        analysis_level="measurement_rows",
        group_statistics=group_statistics,
        declared_units=plan.declared_units,
        source_record_references=source_references,
        independent_biological_n=None,
        input_artifact_sha256=plan.input_artifact_sha256,
        source_sha256=import_result.input_file.sha256,
        confirmed_plan_sha256=confirmed_plan_sha256,
        statistical_limitations=STATISTICAL_LIMITATIONS,
    )


__all__ = ["STATISTICAL_LIMITATIONS", "compute_grouped_descriptive"]
