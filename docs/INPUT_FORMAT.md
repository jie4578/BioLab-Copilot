# Phase 1 input format and structural QC contract

Phase 1 requires the user to select the experiment type explicitly and submit an exact source-column-to-canonical-field mapping. File names, worksheet names, and header similarity never select an experiment type or apply a mapping automatically.

## Generic grouped

Minimum canonical fields:

| Field | Type | Required rule | Structural meaning |
| --- | --- | --- | --- |
| `sample_id` | text identifier | Required for every record | Preserved as text, including `001` and `NA` |
| `group` | text category | Required for every record | Empty values are errors |
| `measurement` | finite number | Required for every record | `0` is valid; NaN, Infinity, locale commas, percent signs, and unit conversion are not guessed |

Optional canonical fields:

| Field | Type | Rule |
| --- | --- | --- |
| `unit` | text | Declared unit for the mapped measurement field; mixed units are an error |
| `replicate_id` | text identifier | Preserved without aggregation |
| `replicate_type` | `biological`, `technical`, or `unknown` | Missing information is represented as `unknown` and warned |
| `biological_replicate_id` | text identifier | Optional design metadata; never inferred |
| `technical_replicate_id` | text identifier | Optional design metadata; never inferred |

One non-empty group can be imported, but it receives `SINGLE_OBSERVATION_GROUP`; statistical sufficiency is not assessed in Phase 1.

## ELISA standard curve

Minimum canonical fields:

| Field | Type | Required rule | Structural meaning |
| --- | --- | --- | --- |
| `sample_id` | text identifier | Required for every record | Preserved as text |
| `sample_type` | enum | Required; `standard`, `sample`, `blank`, or `control` | Unsupported values are errors |
| `measurement` | finite number | Required for every record | No blank correction or fitting is performed |

Conditional and optional fields:

| Field | Type | Rule |
| --- | --- | --- |
| `standard_concentration` | finite number | Required and finite for `sample_type=standard`; optional and preserved as missing for unknown samples |
| `unit` | text | Optional generic declared unit |
| `measurement_unit` | text | Optional response unit; mixed values are errors |
| `concentration_unit` | text | Optional standard/sample concentration unit; mixed values are errors |
| `dilution_factor` | positive finite number | Optional; no conversion is performed |
| `group` | text | Optional descriptive category |
| `replicate_id` | text identifier | Optional design metadata; no averaging |
| `replicate_type` | `biological`, `technical`, or `unknown` | Missing information is represented as `unknown` and warned |
| `biological_replicate_id` | text identifier | Optional design metadata; never inferred |
| `technical_replicate_id` | text identifier | Optional design metadata; never inferred |

Same-concentration standard wells are not duplicate errors by themselves. Only exact duplicate source records receive `DUPLICATE_COMPLETE_RECORD` warnings, and every record is retained.

## Mapping and parsing rules

The mapping direction is `{source_column: canonical_field}`. Source headers must match exactly. Missing source columns, duplicate target fields, unsupported canonical fields, and missing required mappings are blocking issues. The `suggest-mapping` command can report candidates, but it never applies them.

CSV defaults are `utf-8-sig` and comma. This accepts UTF-8 and UTF-8 BOM. Other encodings and delimiters require explicit CLI options. CSV logical record numbers are used; physical line numbers are not claimed for quoted multiline fields.

XLSX input is read in formula-preserving mode with links and macros disabled. Only `.xlsx` is supported. Multiple worksheets require an explicit `--sheet`. Mapped formula cells are blocking issues. Excel row numbers and worksheet names are retained in source locations.

The importer preserves raw source values, parsed canonical values, source locations, the mapping, parser configuration, and the source SHA-256. It does not infer pairing, sample size, replicate independence, units, decimal conventions, or statistical readiness.

## Analysis readiness

`analysis_ready=false` whenever any `error` or `blocking` issue exists, including invalid required values, unsupported categorical values, mixed units, formula cells in mapped fields, missing standard concentrations, or structural mapping failures. Diagnostics and all read records remain available even when analysis is not ready.

For Phase 2A, this flag means only that the Phase 1 import and structural QC passed. It does not
mean that observations are biologically independent, that a design is suitable for inference, or
that any later statistical conclusion is valid.
