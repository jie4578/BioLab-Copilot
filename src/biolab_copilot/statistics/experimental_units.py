"""Experimental-unit validation and deterministic preview construction for Phase 2B."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from biolab_copilot.contracts import (
    ExperimentalGroupPreview,
    ExperimentalUnitPreviewRow,
    ExperimentalUnitRecord,
    ExperimentalUnitsPreview,
    ImportResult,
    IndependentTwoGroupDesign,
    IssueSeverity,
    ValidationIssue,
)


@dataclass(frozen=True)
class PreviewBuild:
    """Preview plus the complete diagnostic set used by plan generation."""

    preview: ExperimentalUnitsPreview
    issues: tuple[ValidationIssue, ...]


def _issue(
    code: str,
    message: str,
    suggested_action: str,
    *,
    severity: IssueSeverity,
    location: str,
    record_number: int | None = None,
    source_file: str | None = None,
    source_row_number: int | None = None,
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        location=location,
        suggested_action=suggested_action,
        source_file=source_file,
        record_number=record_number,
        source_row_number=source_row_number,
        field=field,
        raw_value=None if raw_value is None else str(raw_value)[:200],
    )


def _record_issue(
    record: Any,
    code: str,
    message: str,
    suggested_action: str,
    *,
    severity: IssueSeverity,
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    location = record.source_locations.get(
        field or "experimental_unit_id",
        f"file={record.source_file}; record={record.record_number}",
    )
    return _issue(
        code,
        message,
        suggested_action,
        severity=severity,
        location=location,
        record_number=record.record_number,
        source_file=record.source_file,
        source_row_number=record.source_row_number,
        field=field,
        raw_value=raw_value,
    )


def _finite_mean(values: list[float]) -> float | None:
    try:
        value = math.fsum(values) / len(values)
    except (OverflowError, ZeroDivisionError):
        return None
    return value if math.isfinite(value) else None


def build_experimental_units_preview(
    import_result: ImportResult,
    design: IndependentTwoGroupDesign,
    *,
    preview_id: str,
    input_artifact_sha256: str,
) -> PreviewBuild:
    """Assign source records to explicit experimental units without guessing design."""

    warnings: list[ValidationIssue] = []
    blocking_reasons: list[ValidationIssue] = []
    all_issues: list[ValidationIssue] = []
    rows: list[ExperimentalUnitPreviewRow] = []
    records_by_unit: dict[str, list[Any]] = defaultdict(list)
    unit_groups: dict[str, set[str]] = defaultdict(set)
    valid_groups: set[str] = set()

    if import_result.experiment_type != "generic_grouped":
        issue = _issue(
            "UNSUPPORTED_INPUT_ASSAY",
            "Phase 2B supports only the generic_grouped import artifact.",
            "Use a generic_grouped Phase 1 import result.",
            severity=IssueSeverity.BLOCKING,
            location="import_result.experiment_type",
            field="experiment_type",
            raw_value=import_result.experiment_type,
        )
        blocking_reasons.append(issue)
        all_issues.append(issue)
    if design.experimental_unit_id_field != "experimental_unit_id":
        issue = _issue(
            "UNSUPPORTED_EXPERIMENTAL_UNIT_FIELD",
            "Phase 2B requires the canonical experimental_unit_id field.",
            "Declare experimental_unit_id explicitly in the design file and column mapping.",
            severity=IssueSeverity.BLOCKING,
            location="analysis_plan.experimental_unit_id_field",
            field="experimental_unit_id_field",
            raw_value=design.experimental_unit_id_field,
        )
        blocking_reasons.append(issue)
        all_issues.append(issue)

    for issue in import_result.validation_issues:
        if issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}:
            blocking_reasons.append(issue)
            all_issues.append(issue)
        elif issue.severity == IssueSeverity.WARNING:
            warnings.append(issue)
            all_issues.append(issue)
        if issue.code == "DUPLICATE_COMPLETE_RECORD":
            inferential_issue = _issue(
                "DUPLICATE_COMPLETE_RECORD_INFERENTIAL",
                "A duplicate complete source record blocks Phase 2B inference.",
                (
                    "Resolve or explain the source duplication in a reviewed source export; "
                    "do not repeat-count it for inference."
                ),
                severity=IssueSeverity.BLOCKING,
                location=issue.location,
                record_number=issue.record_number,
                source_file=issue.source_file,
                source_row_number=issue.source_row_number,
                field=issue.field,
                raw_value=issue.raw_value,
            )
            blocking_reasons.append(inferential_issue)
            all_issues.append(inferential_issue)
    if not import_result.analysis_ready:
        issue = _issue(
            "IMPORT_QC_NOT_READY",
            "The Phase 1 import is not structurally analysis-ready.",
            "Resolve all Phase 1 error/blocking issues and create a new import artifact.",
            severity=IssueSeverity.BLOCKING,
            location="import_result.dataset_profile",
        )
        if not any(existing.code == issue.code for existing in blocking_reasons):
            blocking_reasons.append(issue)
            all_issues.append(issue)

    for record in import_result.records:
        parsed = record.parsed_values
        unit_id = parsed.get("experimental_unit_id")
        group = parsed.get("group")
        measurement = parsed.get("measurement")
        technical_repeat_id = parsed.get("technical_replicate_id")
        row_issue_codes: list[str] = []
        if not isinstance(unit_id, str) or not unit_id.strip():
            issue = _record_issue(
                record,
                "EXPERIMENTAL_UNIT_ID_MISSING",
                "Every participating record must have a non-empty experimental_unit_id.",
                (
                    "Map and provide the explicit experimental_unit_id; do not derive it "
                    "from sample_id."
                ),
                severity=IssueSeverity.BLOCKING,
                field="experimental_unit_id",
                raw_value=unit_id,
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)
            row_issue_codes.append(issue.code)
        if not isinstance(group, str) or not group.strip():
            issue = _record_issue(
                record,
                "EXPERIMENTAL_UNIT_GROUP_MISSING",
                "Every participating record must have a non-empty group.",
                "Resolve the Phase 1 group-field issue without inferring a group.",
                severity=IssueSeverity.BLOCKING,
                field="group",
                raw_value=group,
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)
            row_issue_codes.append(issue.code)
        if (
            isinstance(measurement, bool)
            or not isinstance(measurement, int | float)
            or not math.isfinite(float(measurement))
        ):
            issue = _record_issue(
                record,
                "EXPERIMENTAL_UNIT_MEASUREMENT_INVALID",
                "Every participating record must have a finite numeric measurement.",
                "Resolve the Phase 1 measurement-field issue without imputation or transformation.",
                severity=IssueSeverity.BLOCKING,
                field="measurement",
                raw_value=measurement,
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)
            row_issue_codes.append(issue.code)
        rows.append(
            ExperimentalUnitPreviewRow(
                record_number=record.record_number,
                experimental_unit_id=unit_id if isinstance(unit_id, str) else None,
                group=group if isinstance(group, str) else None,
                measurement=float(measurement)
                if isinstance(measurement, int | float)
                and not isinstance(measurement, bool)
                and math.isfinite(float(measurement))
                else None,
                technical_repeat_id=(
                    technical_repeat_id
                    if isinstance(technical_repeat_id, str) and technical_repeat_id.strip()
                    else None
                ),
                source_location=record.source_locations.get(
                    "experimental_unit_id",
                    f"file={record.source_file}; record={record.record_number}",
                ),
                issue_codes=row_issue_codes,
            )
        )
        if (
            isinstance(unit_id, str)
            and unit_id.strip()
            and isinstance(group, str)
            and group.strip()
            and isinstance(measurement, int | float)
            and not isinstance(measurement, bool)
            and math.isfinite(float(measurement))
        ):
            records_by_unit[unit_id].append(record)
            unit_groups[unit_id].add(group)
            valid_groups.add(group)

    for unit_id, groups in sorted(unit_groups.items()):
        if len(groups) > 1:
            issue = _issue(
                "EXPERIMENTAL_UNIT_CROSSES_GROUPS",
                "One experimental_unit_id occurs in both planned groups.",
                (
                    "Correct the explicit experimental-unit identifiers; do not add group "
                    "prefixes automatically."
                ),
                severity=IssueSeverity.BLOCKING,
                location=f"experimental_unit_id={unit_id!r}",
                field="experimental_unit_id",
                raw_value=unit_id,
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)

    units: list[ExperimentalUnitRecord] = []
    for unit_id in sorted(records_by_unit):
        records = sorted(records_by_unit[unit_id], key=lambda record: record.record_number)
        groups = unit_groups[unit_id]
        if len(groups) != 1:
            continue
        group = next(iter(groups))
        measurements = [float(record.parsed_values["measurement"]) for record in records]
        technical_ids = [record.parsed_values.get("technical_replicate_id") for record in records]
        nonempty_technical_ids = [
            value for value in technical_ids if isinstance(value, str) and value
        ]
        if len(records) > 1 and design.technical_repeat_policy == "none":
            issue = _issue(
                "MULTIPLE_MEASUREMENTS_PER_UNIT_NONE_POLICY",
                (
                    "The none technical-repeat policy found multiple measurements for one "
                    "experimental unit."
                ),
                (
                    "Use one record per unit or explicitly declare mean after confirming "
                    "technical-repeat identity."
                ),
                severity=IssueSeverity.BLOCKING,
                location=f"experimental_unit_id={unit_id!r}",
                field="technical_repeat_policy",
                raw_value=len(records),
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)
            continue
        if len(records) > 1 and design.technical_repeat_policy == "mean":
            if len(nonempty_technical_ids) != len(records):
                issue = _issue(
                    "TECHNICAL_REPLICATE_ID_REQUIRED",
                    (
                        "Multiple records under mean policy require a non-empty "
                        "technical_replicate_id for every record."
                    ),
                    (
                        "Declare unique technical_replicate_id values; unknown repeats "
                        "are not auto-classified."
                    ),
                    severity=IssueSeverity.BLOCKING,
                    location=f"experimental_unit_id={unit_id!r}",
                    field="technical_replicate_id",
                )
                blocking_reasons.append(issue)
                all_issues.append(issue)
                continue
            if len(set(nonempty_technical_ids)) != len(nonempty_technical_ids):
                issue = _issue(
                    "TECHNICAL_REPLICATE_ID_NOT_UNIQUE",
                    "Technical replicate IDs must be unique within an experimental unit.",
                    (
                        "Correct the technical replicate identifiers without silently "
                        "deduplicating rows."
                    ),
                    severity=IssueSeverity.BLOCKING,
                    location=f"experimental_unit_id={unit_id!r}",
                    field="technical_replicate_id",
                )
                blocking_reasons.append(issue)
                all_issues.append(issue)
                continue
            if any(record.parsed_values.get("replicate_type") != "technical" for record in records):
                issue = _issue(
                    "TECHNICAL_REPEAT_TYPE_NOT_DECLARED",
                    (
                        "Multiple records under mean policy must be explicitly declared "
                        "technical repeats."
                    ),
                    (
                        "Set replicate_type=technical only when the experimental design "
                        "supports it; unknown is not auto-converted."
                    ),
                    severity=IssueSeverity.BLOCKING,
                    location=f"experimental_unit_id={unit_id!r}",
                    field="replicate_type",
                )
                blocking_reasons.append(issue)
                all_issues.append(issue)
                continue
        aggregated_value = measurements[0] if len(measurements) == 1 else _finite_mean(measurements)
        if aggregated_value is None:
            issue = _issue(
                "NON_FINITE_AGGREGATED_VALUE",
                "Technical-repeat aggregation produced a non-finite value.",
                "Review finite source values; no replacement or overflow masking is applied.",
                severity=IssueSeverity.BLOCKING,
                location=f"experimental_unit_id={unit_id!r}",
                field="measurement",
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)
            continue
        units.append(
            ExperimentalUnitRecord(
                experimental_unit_id=unit_id,
                group=group,
                n_measurements=len(records),
                technical_repeat_count=len(records),
                technical_repeat_ids=nonempty_technical_ids,
                measurement_values=measurements,
                aggregated_value=aggregated_value,
                source_record_numbers=[record.record_number for record in records],
                source_locations=[
                    record.source_locations.get("measurement", record.source_file)
                    for record in records
                ],
            )
        )

    planned_groups = {design.group_a, design.group_b}
    if valid_groups != planned_groups:
        issue = _issue(
            "EXACTLY_TWO_PLANNED_GROUPS_REQUIRED",
            "The data groups do not exactly match the two groups explicitly named in the design.",
            (
                "Declare exactly two observed groups using the original group values; "
                "no group is inferred."
            ),
            severity=IssueSeverity.BLOCKING,
            location="group",
            field="group",
            raw_value=sorted(valid_groups),
        )
        blocking_reasons.append(issue)
        all_issues.append(issue)

    group_previews: list[ExperimentalGroupPreview] = []
    for group in (design.group_a, design.group_b):
        group_units = [unit for unit in units if unit.group == group]
        n_measurements = sum(unit.n_measurements for unit in group_units)
        counts = {unit.experimental_unit_id: unit.technical_repeat_count for unit in group_units}
        group_previews.append(
            ExperimentalGroupPreview(
                group=group,
                n_measurements=n_measurements,
                n_experimental_units=len(group_units),
                technical_repeat_counts=counts,
            )
        )
        if len(group_units) < 2:
            issue = _issue(
                "MINIMUM_EXPERIMENTAL_UNITS_NOT_MET",
                (
                    "Each planned group requires at least two experimental units for "
                    "Welch computation."
                ),
                (
                    "Provide at least two explicit experimental units per group; this is "
                    "only a calculation minimum."
                ),
                severity=IssueSeverity.BLOCKING,
                location=f"group={group!r}",
                field="experimental_unit_id",
                raw_value=len(group_units),
            )
            blocking_reasons.append(issue)
            all_issues.append(issue)
        counts_set = set(counts.values())
        if design.technical_repeat_policy == "mean" and len(counts_set) > 1:
            warning = _issue(
                "TECHNICAL_REPLICATE_COUNT_DIFFERS",
                "Technical replicate counts differ between experimental units in this group.",
                "Review the design; units remain equally weighted after within-unit means.",
                severity=IssueSeverity.WARNING,
                location=f"group={group!r}",
                field="technical_repeat_count",
                raw_value=counts,
            )
            warnings.append(warning)
            all_issues.append(warning)

    independence_warning = _issue(
        "INDEPENDENCE_USER_DECLARED_NOT_VERIFIED",
        "Independence is a user declaration and was not scientifically verified by software.",
        "Review the experimental design and retain the declaration as an explicit assumption.",
        severity=IssueSeverity.WARNING,
        location="analysis_plan.independence_declared",
        field="independence_declared",
    )
    warnings.append(independence_warning)
    all_issues.append(independence_warning)

    preview = ExperimentalUnitsPreview(
        preview_id=preview_id,
        input_artifact_sha256=input_artifact_sha256,
        source_sha256=import_result.input_file.sha256,
        design_type=design.design_type,
        group_a=design.group_a,
        group_b=design.group_b,
        technical_repeat_policy=design.technical_repeat_policy,
        rows=rows,
        units=sorted(units, key=lambda unit: (unit.group, unit.experimental_unit_id)),
        groups=group_previews,
        warnings=warnings,
        blocking_reasons=blocking_reasons,
        preview_ready=not blocking_reasons,
    )
    return PreviewBuild(preview=preview, issues=tuple(all_issues))


__all__ = ["PreviewBuild", "build_experimental_units_preview"]
