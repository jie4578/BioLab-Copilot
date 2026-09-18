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

## Phase 2B restricted Welch comparison

Phase 2B supports exactly one `generic_grouped` measurement endpoint, two explicitly named
groups, and a user-declared `independent_two_group` design. The software records
`independence_status=user_declared_not_verified`: a declaration is not evidence that the units
are independent, and the software does not verify the scientific design. `experimental_unit_id`
is required for every participating record. `biological_replicate_id` and `sample_id` are not
silently reinterpreted as experimental units.

The `none` policy requires exactly one measurement record per experimental unit. The `mean`
policy is allowed only when the user has declared technical repeats, every repeated row has a
unique within-unit `technical_replicate_id`, and `replicate_type=technical`. Within-unit values
are combined by an arithmetic mean; each experimental unit then receives equal weight. All
source record numbers and locations are retained. Different repeat counts generate a warning.
No unknown repeat is converted, no row is deleted, and `independent_biological_n` remains
`null`.

The Welch calculation uses `scipy.stats.ttest_ind(a, b, equal_var=False,
alternative="two-sided", nan_policy="raise")` on aggregated experimental-unit values. Each
group reports measurement count, experimental-unit count, mean, and sample SD (`ddof=1`). The
reported difference is `mean(group_a) - mean(group_b)` in the declared original unit. The 95%
confidence interval uses the same direction and Welch standard error/degrees-of-freedom
formula. A two-unit-per-group minimum is a computation precondition only; it is not a claim of
sufficient sample size, power, normality, or scientifically valid independence.

Both groups with zero variance, zero/non-finite standard error, overflow, non-finite SciPy
outputs, and p-value underflow are failed runs. One zero-variance group may produce a finite
result with an explicit warning. No p-value is described as the probability that the null is
true, and no result is described as causal, efficacious, or statistically conclusive.

## Phase 3A standard-only 4PL

Phase 3A is limited to one `elisa_standard_curve` context and a user-selected direction. For
`x>0`, the deterministic model is:

`y = L + (U-L) * expit(s * B * (log(x) - log(C)))`

where `L` is `lower_asymptote`, `U` is `upper_asymptote` with `U>L`, `C` is
`midpoint_concentration` with `C>0`, `B` is `slope_magnitude` with `B>0`, and `s` is `+1` for
`increasing` or `-1` for `decreasing`. At `x=0`, the analytic limit is `L` for increasing and
`U` for decreasing. The implementation uses `log` and SciPy `expit`; it does not calculate
`x**B`, `C/x`, or `log(0)`.

Only standard rows participate. Sample, blank, and control rows remain in the imported data and
preview but are excluded with reasons. Standard concentration units and response units are user
declared and checked; no unit conversion, blank subtraction, normalization, or dilution-factor
correction occurs. Standard concentrations must be finite and nonnegative, responses must be
finite, and at least six distinct positive concentration levels are required. This is an
engineering protection condition, not a general scientific sufficiency claim.

With `standard_replicate_policy=none`, a concentration level has exactly one record. With
`mean_by_concentration`, explicit unique repeat identifiers are required and records at one
concentration are averaged arithmetically. Fit levels are equally weighted even when raw repeat
counts differ. The fit result reports both `n_fit_levels` and `n_raw_standard_measurements`,
source record references, per-level observed/predicted/residual values, and repeat counts.

The fit uses float64, non-weighted raw-response least squares with `loss=linear`, explicit finite
multi-starts, deterministic numerical bounds, and a fixed evaluation budget. `RMSE` is
`sqrt(SSE / n_fit_levels)`, not a residual standard error. `R²` is descriptive and calculated
only over fitted concentration levels; it may be negative and is `null` when its denominator is
zero. Jacobian rank, condition number, boundary proximity, midpoint span, and monotonicity are
diagnostics, not assay validation criteria. A successful numerical result always states
`curve_validated=false` and `quantification_enabled=false`; it does not calculate unknown sample
concentrations or establish LLOQ/ULOQ, detection range, efficacy, causality, or a validated EC50.
