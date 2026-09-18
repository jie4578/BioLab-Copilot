# Phase 3A ELISA 4PL definitions

Phase 3A implements a narrow, offline standard-only workflow. It does not calculate unknown
sample concentrations, apply blank correction, choose a direction, choose between 4PL and 5PL,
or claim that a curve is validated.

## Scope and input boundary

The input must be a Phase 1 `elisa_standard_curve` artifact with a user-confirmed
`ELISA4PLDesign`. The declaration identifies one curve context, concentration unit, response unit,
direction, standard replicate policy, optimizer settings, parameter bounds generated from the
input, initial starts, and numerical diagnostic thresholds. These bounds are implementation
settings, not biological facts.

Only `sample_type=standard` records are eligible. `sample`, `blank`, and `control` records are
kept in the imported artifact and standards preview with explicit exclusion reasons. They do not
participate in fitting and no concentration result is created for them. Any import error or
blocking QC issue blocks the fit.

At least six distinct positive standard concentrations are required. A zero level is optional
and is evaluated by the analytic limit; zero is never passed to `log`. Negative concentrations,
non-finite concentrations/responses, and duplicate complete standard records block the fit.
Response values may be negative and are not automatically treated as outliers.

## Model semantics

For `x > 0`:

```text
y = L + (U - L) * expit(s * B * (log(x) - log(C)))
```

`L` is `lower_asymptote`, `U` is `upper_asymptote`, `C` is `midpoint_concentration`, and `B`
is `slope_magnitude`. The constraints are `U > L`, `C > 0`, and `B > 0`. `s=+1` for an
increasing curve and `s=-1` for a decreasing curve. At `x=0`, the result is `L` for increasing
and `U` for decreasing. `C` is not called a validated pharmacological EC50.

The fit is non-weighted least squares on the original response scale with `loss=linear`. It uses
float64, SciPy `least_squares`, stable `expit` evaluation, deterministic bounded starts, and a
fixed `max_nfev` budget. No random search, fallback direction, automatic point removal, robust
loss, transformation, or unit conversion is allowed.

## Replicate policy

`none` requires exactly one standard record at each concentration. `mean_by_concentration`
requires a declared repeat-ID field and unique repeat IDs within every concentration. Values are
averaged arithmetically within concentration; concentration levels are equally weighted even if
their raw replicate counts differ. The preview and result retain all source record references,
replicate counts, means, and sample SDs. Unequal replicate counts produce a warning.

## Diagnostics and status

The result reports per-level observed/predicted/residual values, `SSE`,
`RMSE=sqrt(SSE/n_fit_levels)`, descriptive fitted-level `R²`, every optimizer-start outcome,
termination information, boundary proximity, Jacobian rank/condition, midpoint location relative
to the observed positive span, and monotonicity/repeat-count warnings. A zero denominator makes
`R²=null` with a reason. Warnings do not become scientific validation.

Every computed result has `curve_validated=false` and `quantification_enabled=false`. The observed
standard concentration span is not an LLOQ, ULOQ, detection range, or validated quantification
range. A user declaration of one curve context and a numerical convergence result do not prove
assay suitability, standard/sample independence, normality, or causal efficacy.
