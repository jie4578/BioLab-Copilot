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
| `experimental_unit_id` | text identifier | Optional Phase 2B design field; must be explicitly mapped and supplied for every inferential record |
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

## Phase 2B design input

Phase 2B accepts only a `generic_grouped` artifact with one mapped `measurement` field and an
explicit user-supplied design declaration. The declaration is a separate JSON object containing:

| Field | Required value or type | Meaning |
| --- | --- | --- |
| `design_type` | `independent_two_group` | Restricted supported design |
| `experimental_unit_id_field` | `experimental_unit_id` | Canonical field used to identify one experimental unit |
| `group_a`, `group_b` | two different non-empty original group values | Planned comparison groups |
| `technical_repeat_policy` | `none` or `mean` | Explicit record handling rule |
| `method` | `welch_t` | Two-sided Welch comparison only |
| `alternative` | `two-sided` | No one-sided alternative is accepted |
| `alpha` | `0.05` | Fixed significance level for the comparison |
| `confidence_level` | `0.95` | Fixed mean-difference interval level |
| `independence_declared` | `true` | User declaration, not software verification |
| `assumptions_acknowledged` | `true` | User acknowledgement of the stated assumptions |

`biological_replicate_id` is not an experimental-unit declaration, and `sample_id` keeps its
Phase 1 meaning. The software never derives unit IDs, pairing, independence, or biological
sample size. Every participating row must have a non-empty unit ID, and one ID may not occur in
both groups.

With `technical_repeat_policy=none`, each unit must have exactly one measurement row. With
`mean`, multiple rows require unique `technical_replicate_id` values and
`replicate_type=technical` for that unit. Values are averaged arithmetically within a unit and
each unit receives equal weight. All source rows and locations remain in the preview. Unknown
repeat types are not converted to technical repeats.

## Phase 3A standard-curve fit declaration

Phase 3A requires a separate JSON `ELISA4PLDesign` declaration. The user must explicitly provide:

| Field | Allowed values or rule |
| --- | --- |
| `curve_context_declared` | `true`; one file represents one declared curve context |
| `concentration_unit` | Non-empty declared concentration unit; no conversion |
| `response_unit` | Non-empty declared response unit; no conversion |
| `direction` | `increasing` or `decreasing`; no automatic selection |
| `standard_replicate_policy` | `none` or `mean_by_concentration` |
| `standard_repeat_id_field` | Required and explicit for mean-by-concentration; `replicate_id` or `technical_replicate_id` |
| `blank_policy`, `weighting`, `loss` | Exactly `none`, `none`, and `linear` |
| optimizer settings | Explicit SciPy least-squares tolerances, evaluation budget, starts, bounds, and diagnostic thresholds |

Only `sample_type=standard` records with finite nonnegative `standard_concentration` and finite
`measurement` can enter the preview. At least six distinct positive concentration levels are an
engineering precondition for this implementation; an optional zero level is retained using the
analytic 4PL limit. `sample`, `blank`, and `control` records are preserved with an exclusion
reason and do not receive a calculated concentration.

With `none`, each concentration level must have exactly one standard record. With
`mean_by_concentration`, same-concentration records require unique explicit repeat IDs and are
averaged arithmetically within the level; concentration levels, not wells, are equally weighted.
Duplicate complete standard records block fitting. Unequal repeat counts warn but do not change
level weighting. A changed source artifact, mapping, design declaration, preview, direction,
numerical setting, or plan invalidates the previous plan hash confirmation.
