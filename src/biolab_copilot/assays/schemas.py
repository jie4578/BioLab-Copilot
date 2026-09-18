"""Phase 1 input field contracts for the supported assay types.

These schemas describe structure only. They do not perform statistics, fitting, or
aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssayFieldSchema:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    numeric_fields: tuple[str, ...]
    identifier_fields: tuple[str, ...]
    allowed_values: dict[str, frozenset[str]]

    @property
    def allowed_fields(self) -> frozenset[str]:
        return frozenset((*self.required_fields, *self.optional_fields))


GENERIC_GROUPED_SCHEMA = AssayFieldSchema(
    required_fields=("sample_id", "group", "measurement"),
    optional_fields=(
        "unit",
        "experimental_unit_id",
        "replicate_id",
        "replicate_type",
        "biological_replicate_id",
        "technical_replicate_id",
    ),
    numeric_fields=("measurement",),
    identifier_fields=(
        "sample_id",
        "experimental_unit_id",
        "replicate_id",
        "biological_replicate_id",
        "technical_replicate_id",
    ),
    allowed_values={"replicate_type": frozenset({"biological", "technical", "unknown"})},
)


ELISA_STANDARD_CURVE_SCHEMA = AssayFieldSchema(
    required_fields=("sample_id", "sample_type", "measurement"),
    optional_fields=(
        "group",
        "unit",
        "measurement_unit",
        "concentration_unit",
        "standard_concentration",
        "dilution_factor",
        "replicate_id",
        "replicate_type",
        "biological_replicate_id",
        "technical_replicate_id",
    ),
    numeric_fields=("measurement", "standard_concentration", "dilution_factor"),
    identifier_fields=(
        "sample_id",
        "replicate_id",
        "biological_replicate_id",
        "technical_replicate_id",
    ),
    allowed_values={
        "sample_type": frozenset({"standard", "sample", "blank", "control"}),
        "replicate_type": frozenset({"biological", "technical", "unknown"}),
    },
)


ASSAY_SCHEMAS: dict[str, AssayFieldSchema] = {
    "generic_grouped": GENERIC_GROUPED_SCHEMA,
    "elisa_standard_curve": ELISA_STANDARD_CURVE_SCHEMA,
}


def get_assay_schema(experiment_type: str) -> AssayFieldSchema:
    """Return the explicit schema for a supported experiment type."""

    try:
        return ASSAY_SCHEMAS[experiment_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported experiment type: {experiment_type}") from exc


def suggest_column_mapping(source_columns: list[str], experiment_type: str) -> dict[str, list[str]]:
    """Suggest exact or normalized header candidates without selecting any mapping."""

    schema = get_assay_schema(experiment_type)
    suggestions: dict[str, list[str]] = {}
    normalized = {column.strip().lower(): column for column in source_columns}
    for field in sorted(schema.allowed_fields):
        candidate = normalized.get(field.lower())
        if candidate is not None:
            suggestions[field] = [candidate]
    return suggestions


__all__ = [
    "ASSAY_SCHEMAS",
    "ELISA_STANDARD_CURVE_SCHEMA",
    "GENERIC_GROUPED_SCHEMA",
    "AssayFieldSchema",
    "get_assay_schema",
    "suggest_column_mapping",
]
