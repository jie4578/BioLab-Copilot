# ELISA 4PL inverse definitions — Phase 3B

Phase 3B provides a research-use numerical estimate for each `sample` measurement row using an
unchanged, confirmed Phase 3A 4PL result. It is not validated assay quantification. Every result
contains `intended_use=research_only`, `curve_validated=false`,
`validated_quantification_enabled=false`, and `research_estimation_enabled=true`.

## Curve preconditions

The curve must be a computed, converged Phase 3A 4PL with finite parameters
`L=lower_asymptote`, `U=upper_asymptote`, `C=midpoint_concentration`, and
`B=slope_magnitude`, satisfying `U>L`, `C>0`, and `B>0`. Boundary-limited parameters, a rank
deficient Jacobian, severe ill-conditioning, error/blocking diagnostics, changed plan/preview/
manifest hashes, or a non-converged optimizer block inversion. R² alone never releases a curve.

Phase 3A flags remain false. Software checks structural and numerical consistency; it does not
verify assay accuracy, precision, matrix compatibility, experimental context, or calibration
validity.

## Per-row inverse

For `L < y < U`:

```text
log(x) = log(C) + (s / B) * (log(y - L) - log(U - y))
```

where `s=+1` for increasing and `s=-1` for decreasing. The implementation protects the
exponentiation, never takes a logarithm of zero, never clips a response, and checks the result by
forward substitution through the 4PL.

The permitted interpolation span is:

```text
[min_positive_standard_concentration,
 max_positive_standard_concentration]
```

The zero-concentration standard can be part of the fit but is not the inverse span lower bound.
The endpoints' response limits are predicted from the fitted curve, not taken from raw response
minimum/maximum values. This span is not an LLOQ, ULOQ, detection range, or validated
quantification range.

Rows outside that span receive null concentration fields and one of the stable statuses
`below_standard_span` or `above_standard_span`. Model-domain and numerical statuses are
`outside_model_domain`, `near_asymptote_unstable`, and `numerical_failure`. The direction of
these concentration statuses is independent of response monotonicity.

## Dilution correction

The plan must explicitly select either `mapped_field` for the canonical `dilution_factor` field
or `uniform_declared` for one finite factor. Factors must be at least 1; undiluted input must
explicitly state 1. No factor is inferred or silently defaulted. For a successful estimate only:

```text
concentration_in_original_sample = concentration_in_assayed_sample * dilution_factor
```

Overflow produces a numerical failure and never JSON `Infinity`. Unknown replicate rows remain
separate; no mean, SD, CV, or biological sample count is calculated.

## Plan and provenance

`analysis_plan.json` binds the curve result, Phase 3A plan, standards preview, curve manifest,
sample import artifact, source hashes, mapping/configuration, explicit design, numeric tolerances,
and a deterministic sample preview. Execution requires explicit confirmation of the final plan
SHA-256 and warning fields. A changed curve, input, preview, design, dilution configuration, or
plan invalidates the old confirmation.

Execution writes `analysis_plan.json`, `sample_concentrations.json`, `analysis_issues.json`, and
`run_manifest.json` in a new directory. Strict JSON is used; no NaN or Infinity is emitted.
