# Phase 2A statistical definitions

Phase 2A supports only `generic_grouped` and only the `measurement_rows` analysis level. It
describes preserved measurement records; it does not estimate independent biological sample
size or make inferential claims.

## Fixed output

For each non-empty group, the deterministic engine emits:

- `n_measurements`: number of preserved measurement records in the group.
- `mean`: arithmetic mean of the finite measurement values.
- `median`: ordinary median of the finite measurement values.
- `min`: minimum measurement value.
- `max`: maximum measurement value.
- `sample_sd`: sample standard deviation with `ddof=1`.

For one measurement, `sample_sd` is JSON `null` with the reason that at least two measurement
rows are required for `ddof=1`. For two or more equal values, `sample_sd` is `0`.

Negative values and zero are valid. Values are checked for finiteness immediately before
calculation. Overflow or any non-finite intermediate/result produces a failed run and no
successful group statistics. No rounding is performed by the calculation layer.

## Repeat and missing-data policy

Technical repeats, biological-repeat metadata, unknown repeats, and duplicate complete records
remain at the measurement-row level. No row is deduplicated, averaged, paired, imputed, removed,
unit-converted, or transformed. `independent_biological_n` is always `null` in Phase 2A.

Duplicate complete records, unknown repeat type, and a single observation group are retained as
warnings. The generated plan lists these warning codes when present; execution requires an
explicit `warning_confirmations` entry for each one. Confirming a warning acknowledges the
decision to describe the preserved records; it does not certify biological independence.

## Traceability

Every executed result records the confirmed plan SHA-256, Phase 1 import-artifact SHA-256, source
file SHA-256, column mapping, declared unit, source record numbers, software version, and
statistical limitations. A changed plan or import artifact invalidates the previous confirmation.

The principal blocking issue codes are `PLAN_NOT_CONFIRMED`, `PLAN_HASH_MISMATCH`,
`REQUIRED_WARNING_NOT_CONFIRMED`, `INPUT_ARTIFACT_HASH_MISMATCH`,
`PARSER_CONFIGURATION_BINDING_MISMATCH`, `COLUMN_MAPPING_BINDING_MISMATCH`,
`IMPORT_QC_NOT_READY`, `UNSUPPORTED_INPUT_ASSAY`, and `NON_FINITE_STATISTIC`. A failed preflight
or failed numeric computation writes diagnostics and a failed `AnalysisResult`; it never emits a
successful result with silently excluded rows.

Phase 2A is not a scientific validation of assay design and does not produce p-values, tests,
effect sizes, confidence intervals, CV, ELISA concentrations, or conclusions such as
"statistically significant" or "independent samples".
