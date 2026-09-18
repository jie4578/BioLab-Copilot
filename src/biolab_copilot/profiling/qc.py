"""Structural profiling and validation for imported records.

This module deliberately does not calculate CVs, detect outliers, aggregate replicates,
fit curves, or infer statistical sample sizes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from biolab_copilot.assays import AssayFieldSchema, get_assay_schema
from biolab_copilot.contracts import (
    AssayType,
    DatasetProfile,
    FieldProfile,
    ImportedRecord,
    ImportResult,
    IssueSeverity,
    ValidationIssue,
)
from biolab_copilot.ingestion import RawRecord, RawTable


@dataclass
class _FieldStats:
    source_column: str | None
    observed_types: set[str] = field(default_factory=set)
    non_missing_count: int = 0
    missing_count: int = 0
    invalid_count: int = 0
    non_finite_count: int = 0


def _safe_raw_value(value: Any, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _issue(
    *,
    code: str,
    severity: IssueSeverity,
    message: str,
    location: str,
    suggested_action: str,
    source_file: str,
    sheet_name: str | None = None,
    record_number: int | None = None,
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
        sheet_name=sheet_name,
        record_number=record_number,
        source_row_number=source_row_number,
        field=field,
        raw_value=_safe_raw_value(raw_value),
    )


def _source_file(table: RawTable) -> str:
    return Path(table.input_file.path).name


def _dataset_location(table: RawTable) -> str:
    return f"file={_source_file(table)}; sheet={table.sheet_name or '-'}; dataset"


def _record_location(record: RawRecord, field: str | None = None) -> str:
    if field is not None:
        source_location = record.source_locations.get(field)
        if source_location is not None:
            return source_location
    return (
        f"file={record.source_file}; sheet={record.sheet_name or '-'}; "
        f"record={record.record_number}"
    )


def validate_mapping(
    table: RawTable,
    experiment_type: str,
    column_mapping: dict[str, str],
) -> list[ValidationIssue]:
    """Validate an explicit source-column-to-canonical-field mapping."""

    source_file = _source_file(table)
    try:
        schema = get_assay_schema(experiment_type)
    except ValueError:
        return [
            _issue(
                code="UNSUPPORTED_EXPERIMENT_TYPE",
                severity=IssueSeverity.BLOCKING,
                message=f"Unsupported experiment type: {experiment_type}.",
                location=_dataset_location(table),
                suggested_action="Choose a supported experiment type explicitly.",
                source_file=source_file,
            )
        ]
    issues: list[ValidationIssue] = []
    if not column_mapping:
        issues.append(
            _issue(
                code="MAPPING_REQUIRED",
                severity=IssueSeverity.BLOCKING,
                message="An explicit source-column-to-canonical-field mapping is required.",
                location=_dataset_location(table),
                suggested_action='Submit a JSON mapping such as {"source header": "sample_id"}.',
                source_file=source_file,
            )
        )
        return issues
    source_headers = set(table.headers)
    targets: dict[str, list[str]] = defaultdict(list)
    for source_column, canonical_field in column_mapping.items():
        targets[canonical_field].append(source_column)
        if source_column not in source_headers:
            issues.append(
                _issue(
                    code="MAPPED_SOURCE_COLUMN_MISSING",
                    severity=IssueSeverity.BLOCKING,
                    message=(
                        f"Mapped source column {source_column!r} is not present "
                        "in the source header."
                    ),
                    location=_dataset_location(table),
                    suggested_action=(
                        "Use an exact source header from the selected file or worksheet."
                    ),
                    source_file=source_file,
                    field=canonical_field,
                    raw_value=source_column,
                )
            )
        if canonical_field not in schema.allowed_fields:
            issues.append(
                _issue(
                    code="UNSUPPORTED_CANONICAL_FIELD",
                    severity=IssueSeverity.BLOCKING,
                    message=(
                        f"Canonical field {canonical_field!r} is not supported "
                        f"for {experiment_type}."
                    ),
                    location=_dataset_location(table),
                    suggested_action=(
                        "Map only to fields declared by the selected experiment contract."
                    ),
                    source_file=source_file,
                    field=canonical_field,
                    raw_value=canonical_field,
                )
            )
    for target, source_columns in targets.items():
        if len(source_columns) > 1:
            issues.append(
                _issue(
                    code="DUPLICATE_TARGET_FIELD_MAPPING",
                    severity=IssueSeverity.BLOCKING,
                    message=f"Canonical field {target!r} is mapped from multiple source columns.",
                    location=_dataset_location(table),
                    suggested_action="Map each canonical field from exactly one source column.",
                    source_file=source_file,
                    field=target,
                    raw_value=", ".join(source_columns),
                )
            )
    mapped_targets = set(column_mapping.values())
    for required_field in schema.required_fields:
        if required_field not in mapped_targets:
            issues.append(
                _issue(
                    code="MISSING_REQUIRED_FIELD_MAPPING",
                    severity=IssueSeverity.BLOCKING,
                    message=f"Required canonical field {required_field!r} is not mapped.",
                    location=_dataset_location(table),
                    suggested_action="Provide an explicit mapping for every required field.",
                    source_file=source_file,
                    field=required_field,
                )
            )
    return issues


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _observed_type(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number" if math.isfinite(value) else "non_finite"
    if isinstance(value, str):
        return "text"
    return type(value).__name__


def _parse_numeric(value: Any) -> tuple[float | None, str]:
    if _is_missing(value):
        return None, "missing"
    if isinstance(value, bool):
        return None, "invalid"
    try:
        parsed = float(value.strip()) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(parsed):
        return None, "non_finite"
    return parsed, "number"


def _parse_identifier(value: Any) -> tuple[str | None, str, bool]:
    if _is_missing(value):
        return None, "missing", False
    if isinstance(value, str):
        return value, "text", False
    return str(value), "text", True


def _parse_text(value: Any) -> tuple[str | None, str, bool]:
    if _is_missing(value):
        return None, "missing", False
    if isinstance(value, str):
        return value, "text", False
    return str(value), "text", True


def _mapping_reverse(column_mapping: dict[str, str]) -> dict[str, str]:
    return {canonical: source for source, canonical in column_mapping.items()}


def _record_issue(
    *,
    record: RawRecord,
    code: str,
    severity: IssueSeverity,
    message: str,
    suggested_action: str,
    field: str | None = None,
    raw_value: Any = None,
) -> ValidationIssue:
    return _issue(
        code=code,
        severity=severity,
        message=message,
        location=_record_location(record, field),
        suggested_action=suggested_action,
        source_file=record.source_file,
        sheet_name=record.sheet_name,
        record_number=record.record_number,
        source_row_number=record.source_row_number,
        field=field,
        raw_value=raw_value,
    )


def _parse_record(
    record: RawRecord,
    schema: AssayFieldSchema,
    column_mapping: dict[str, str],
    issues: list[ValidationIssue],
    field_stats: dict[str, _FieldStats],
) -> ImportedRecord:
    reverse_mapping = _mapping_reverse(column_mapping)
    parsed: dict[str, Any] = {}
    locations: dict[str, str] = {}
    for canonical_field, source_column in reverse_mapping.items():
        raw_value = record.raw_values.get(source_column)
        stats = field_stats.setdefault(canonical_field, _FieldStats(source_column=source_column))
        stats.observed_types.add(_observed_type(raw_value))
        if source_column in record.formula_columns:
            stats.invalid_count += 1
            issues.append(
                _record_issue(
                    record=record,
                    code="FORMULA_CELL_IN_MAPPED_FIELD",
                    severity=IssueSeverity.BLOCKING,
                    message=(
                        "A formula cell is mapped to an analysis field; its cached value "
                        "is not trusted."
                    ),
                    suggested_action=(
                        "Replace the formula with a reviewed literal source value or provide "
                        "a source export without formulas."
                    ),
                    field=canonical_field,
                    raw_value=raw_value,
                )
            )
            parsed[canonical_field] = None
            locations[canonical_field] = record.source_locations.get(
                source_column,
                (
                    f"file={record.source_file}; record={record.record_number}; "
                    f"missing_column={source_column!r}"
                ),
            )
            continue
        if canonical_field in schema.numeric_fields:
            numeric_value, state = _parse_numeric(raw_value)
            if state == "missing":
                stats.missing_count += 1
            elif state == "invalid":
                stats.invalid_count += 1
                issues.append(
                    _record_issue(
                        record=record,
                        code="INVALID_NUMERIC",
                        severity=IssueSeverity.ERROR,
                        message=(
                            "The mapped numeric field contains text or a value that cannot "
                            "be parsed as a number."
                        ),
                        suggested_action=(
                            "Review the original value and provide an explicit numeric "
                            "representation; do not apply locale guessing."
                        ),
                        field=canonical_field,
                        raw_value=raw_value,
                    )
                )
            elif state == "non_finite":
                stats.non_finite_count += 1
                issues.append(
                    _record_issue(
                        record=record,
                        code="NON_FINITE_NUMERIC",
                        severity=IssueSeverity.ERROR,
                        message="The mapped numeric field contains NaN or Infinity.",
                        suggested_action=(
                            "Replace the non-finite value in a reviewed source copy; preserve "
                            "the original."
                        ),
                        field=canonical_field,
                        raw_value=raw_value,
                    )
                )
            else:
                stats.non_missing_count += 1
            parsed[canonical_field] = numeric_value
        elif canonical_field in schema.identifier_fields:
            identifier_value, state, non_text = _parse_identifier(raw_value)
            if state == "missing":
                stats.missing_count += 1
            else:
                stats.non_missing_count += 1
            if non_text:
                issues.append(
                    _record_issue(
                        record=record,
                        code="NUMERIC_IDENTIFIER_CELL",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "The identifier cell is not text; leading zeros cannot be recovered "
                            "reliably."
                        ),
                        suggested_action=(
                            "Store identifiers as text in the source workbook and verify the "
                            "converted value manually."
                        ),
                        field=canonical_field,
                        raw_value=raw_value,
                    )
                )
            parsed[canonical_field] = identifier_value
        else:
            text_value, state, non_text = _parse_text(raw_value)
            if state == "missing":
                stats.missing_count += 1
            else:
                stats.non_missing_count += 1
            if non_text:
                issues.append(
                    _record_issue(
                        record=record,
                        code="NON_TEXT_TEXT_FIELD",
                        severity=IssueSeverity.WARNING,
                        message="A text field contains a non-text cell value.",
                        suggested_action=(
                            "Review the source cell type and use explicit text values for "
                            "categorical fields."
                        ),
                        field=canonical_field,
                        raw_value=raw_value,
                    )
                )
            parsed[canonical_field] = text_value
        locations[canonical_field] = record.source_locations.get(
            source_column,
            (
                f"file={record.source_file}; record={record.record_number}; "
                f"missing_column={source_column!r}"
            ),
        )

    for required_field in schema.required_fields:
        if required_field not in reverse_mapping:
            parsed[required_field] = None
            field_stats.setdefault(
                required_field, _FieldStats(source_column=None)
            ).missing_count += 1
        elif _is_missing(parsed.get(required_field)):
            code = "EMPTY_GROUP" if required_field == "group" else "MISSING_REQUIRED_VALUE"
            issues.append(
                _record_issue(
                    record=record,
                    code=code,
                    severity=IssueSeverity.ERROR,
                    message=f"Required field {required_field!r} is empty.",
                    suggested_action="Review the source record and provide the required value.",
                    field=required_field,
                    raw_value=record.raw_values.get(reverse_mapping[required_field]),
                )
            )
    if "replicate_type" in schema.allowed_fields:
        if "replicate_type" not in reverse_mapping or _is_missing(parsed.get("replicate_type")):
            parsed["replicate_type"] = "unknown"
        elif parsed.get("replicate_type") not in schema.allowed_values["replicate_type"]:
            issues.append(
                _record_issue(
                    record=record,
                    code="UNSUPPORTED_REPLICATE_TYPE",
                    severity=IssueSeverity.ERROR,
                    message="Replicate type is not one of biological, technical, or unknown.",
                    suggested_action=(
                        "Declare the replicate type explicitly or use unknown; do not infer it."
                    ),
                    field="replicate_type",
                    raw_value=parsed.get("replicate_type"),
                )
            )
    if "sample_type" in schema.allowed_values:
        sample_type = parsed.get("sample_type")
        if sample_type is not None and sample_type not in schema.allowed_values["sample_type"]:
            issues.append(
                _record_issue(
                    record=record,
                    code="UNSUPPORTED_SAMPLE_TYPE",
                    severity=IssueSeverity.ERROR,
                    message="Sample type is not supported by the ELISA input contract.",
                    suggested_action="Use standard, sample, blank, or control explicitly.",
                    field="sample_type",
                    raw_value=sample_type,
                )
            )
        if sample_type == "standard":
            concentration = parsed.get("standard_concentration")
            if "standard_concentration" not in reverse_mapping or _is_missing(concentration):
                issues.append(
                    _record_issue(
                        record=record,
                        code="STANDARD_CONCENTRATION_REQUIRED",
                        severity=IssueSeverity.BLOCKING,
                        message="A standard row must contain a standard concentration.",
                        suggested_action=(
                            "Map standard_concentration explicitly and provide a finite numeric "
                            "value for every standard."
                        ),
                        field="standard_concentration",
                        raw_value=record.raw_values.get(
                            reverse_mapping.get("standard_concentration", "")
                        ),
                    )
                )
    dilution_factor = parsed.get("dilution_factor")
    if dilution_factor is not None and (
        not isinstance(dilution_factor, int | float) or dilution_factor <= 0
    ):
        issues.append(
            _record_issue(
                record=record,
                code="INVALID_DILUTION_FACTOR",
                severity=IssueSeverity.ERROR,
                message="Dilution factor must be a positive finite number when supplied.",
                suggested_action=(
                    "Review the dilution factor; no unit conversion or replacement is applied."
                ),
                field="dilution_factor",
                raw_value=dilution_factor,
            )
        )
    return ImportedRecord(
        record_number=record.record_number,
        source_file=record.source_file,
        sheet_name=record.sheet_name,
        source_row_number=record.source_row_number,
        raw_values=record.raw_values,
        parsed_values=parsed,
        source_locations=locations,
    )


def _has_error(issue: ValidationIssue) -> bool:
    return issue.severity in {IssueSeverity.ERROR, IssueSeverity.BLOCKING}


def profile_and_validate(
    table: RawTable,
    experiment_type: str,
    column_mapping: dict[str, str],
    *,
    parse_configuration: dict[str, Any] | None = None,
) -> ImportResult:
    """Create an immutable import result and structural QC profile."""

    source_file = _source_file(table)
    mapping_issues = validate_mapping(table, experiment_type, column_mapping)
    schema = get_assay_schema(experiment_type)
    issues: list[ValidationIssue] = [*table.issues, *mapping_issues]
    field_stats: dict[str, _FieldStats] = {}
    reverse_mapping = _mapping_reverse(column_mapping)
    records: list[ImportedRecord] = []
    record_issue_counts: dict[int, int] = defaultdict(int)
    duplicate_record_numbers: list[int] = []
    seen_records: dict[tuple[str, ...], int] = {}
    sample_signatures: dict[str, tuple[Any, ...]] = {}
    group_counts: dict[str, int] = defaultdict(int)
    unit_values: dict[str, set[str]] = defaultdict(set)
    source_missing_count = 0

    for raw_record in table.records:
        source_missing_count += sum(
            1 for header in table.headers if _is_missing(raw_record.raw_values.get(header))
        )
        record_key = tuple(
            repr(raw_record.raw_values.get(key)) for key in sorted(raw_record.raw_values)
        )
        if record_key in seen_records:
            duplicate_record_numbers.append(raw_record.record_number)
            issues.append(
                _record_issue(
                    record=raw_record,
                    code="DUPLICATE_COMPLETE_RECORD",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "This complete source record duplicates an earlier record; all copies "
                        "are retained."
                    ),
                    suggested_action=(
                        "Review whether the duplicate is intentional. No row is deleted "
                        "automatically."
                    ),
                )
            )
        else:
            seen_records[record_key] = raw_record.record_number
        parsed_record = _parse_record(raw_record, schema, column_mapping, issues, field_stats)
        records.append(parsed_record)
        parsed = parsed_record.parsed_values
        group = parsed.get("group")
        if isinstance(group, str) and group.strip():
            group_counts[group] += 1
        for unit_field in ("unit", "measurement_unit", "concentration_unit"):
            unit = parsed.get(unit_field)
            if isinstance(unit, str) and unit.strip():
                unit_values[unit_field].add(unit)
        sample_id = parsed.get("sample_id")
        if isinstance(sample_id, str) and sample_id.strip():
            signature = tuple(
                parsed.get(field_name)
                for field_name in (
                    "group",
                    "sample_type",
                    "unit",
                    "measurement_unit",
                    "concentration_unit",
                )
            )
            previous = sample_signatures.get(sample_id)
            if previous is not None and previous != signature:
                issues.append(
                    _record_issue(
                        record=raw_record,
                        code="IDENTIFIER_CONFLICT",
                        severity=IssueSeverity.ERROR,
                        message=(
                            "The same sample_id is associated with conflicting categorical or "
                            "unit values."
                        ),
                        suggested_action=(
                            "Review the source identifiers and categorical fields; do not infer "
                            "a pairing or aggregate records."
                        ),
                        field="sample_id",
                        raw_value=sample_id,
                    )
                )
            else:
                sample_signatures[sample_id] = signature

    if not table.records:
        issues.append(
            _issue(
                code="EMPTY_DATASET",
                severity=IssueSeverity.BLOCKING,
                message="The selected source contains no logical data records.",
                location=_dataset_location(table),
                suggested_action=(
                    "Provide at least one data record while preserving the original source file."
                ),
                source_file=source_file,
                sheet_name=table.sheet_name,
            )
        )
    if "replicate_type" not in reverse_mapping or all(
        record.parsed_values.get("replicate_type") == "unknown" for record in records
    ):
        issues.append(
            _issue(
                code="REPLICATE_TYPE_UNKNOWN",
                severity=IssueSeverity.WARNING,
                message="Biological versus technical replicate information is missing or unknown.",
                location=_dataset_location(table),
                suggested_action=(
                    "Provide explicit replicate_type and replicate_id fields if the experiment "
                    "design supports them; no records are aggregated."
                ),
                source_file=source_file,
                sheet_name=table.sheet_name,
                field="replicate_type",
            )
        )
    if experiment_type == "generic_grouped" and records and len(group_counts) <= 1:
        issues.append(
            _issue(
                code="SINGLE_OBSERVATION_GROUP",
                severity=IssueSeverity.WARNING,
                message=(
                    "The imported data contains at most one non-empty observation group; "
                    "statistical sufficiency is not confirmed."
                ),
                location=_dataset_location(table),
                suggested_action=(
                    "Confirm the experiment design before any later statistical analysis."
                ),
                source_file=source_file,
                sheet_name=table.sheet_name,
                field="group",
            )
        )
    for unit_field, values in unit_values.items():
        if len(values) > 1:
            issues.append(
                _issue(
                    code="MIXED_UNITS",
                    severity=IssueSeverity.ERROR,
                    message=f"The field {unit_field!r} contains more than one declared unit.",
                    location=_dataset_location(table),
                    suggested_action=(
                        "Review units and provide one explicit unit per measurement field; "
                        "no conversion is applied."
                    ),
                    source_file=source_file,
                    sheet_name=table.sheet_name,
                    field=unit_field,
                    raw_value=", ".join(sorted(values)),
                )
            )

    for issue in issues:
        if issue.record_number is not None and _has_error(issue):
            record_issue_counts[issue.record_number] += 1
    error_record_numbers = set(record_issue_counts)
    parsed_record_count = sum(
        1 for record in records if record.record_number not in error_record_numbers
    )
    field_profiles = [
        FieldProfile(
            field_name=field_name,
            source_column=stats.source_column,
            observed_types=sorted(stats.observed_types),
            non_missing_count=stats.non_missing_count,
            missing_count=stats.missing_count,
            invalid_count=stats.invalid_count,
            non_finite_count=stats.non_finite_count,
        )
        for field_name, stats in sorted(field_stats.items())
    ]
    issue_counts = {
        severity: sum(1 for issue in issues if issue.severity == severity)
        for severity in IssueSeverity
    }
    analysis_ready = not any(_has_error(issue) for issue in issues) and bool(records)
    profile = DatasetProfile(
        dataset_id=Path(table.input_file.path).stem,
        source_filename=source_file,
        source_sha256=table.input_file.sha256,
        row_count=len(records),
        column_count=len(table.headers),
        column_names=list(table.headers),
        missing_value_count=source_missing_count,
        duplicate_row_count=len(duplicate_record_numbers),
        warnings=[issue.code for issue in issues if issue.severity == IssueSeverity.WARNING],
        analysis_ready=analysis_ready,
        parsed_record_count=parsed_record_count,
        error_record_count=len(error_record_numbers),
        warning_count=issue_counts[IssueSeverity.WARNING],
        error_count=issue_counts[IssueSeverity.ERROR],
        blocking_count=issue_counts[IssueSeverity.BLOCKING],
        field_profiles=field_profiles,
        group_counts=dict(sorted(group_counts.items())),
        unit_values={key: sorted(values) for key, values in sorted(unit_values.items())},
        duplicate_record_numbers=duplicate_record_numbers,
        source_sheet_name=table.sheet_name,
    )
    return ImportResult(
        input_file=table.input_file,
        experiment_type=cast(AssayType, experiment_type),
        column_mapping=column_mapping,
        parse_configuration=parse_configuration or {},
        dataset_profile=profile,
        validation_issues=issues,
        records=records,
        analysis_ready=analysis_ready,
    )


__all__ = ["profile_and_validate", "validate_mapping"]
