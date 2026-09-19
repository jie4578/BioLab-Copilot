# BioLab Copilot

BioLab Copilot is a local-first foundation for traceable biological experiment data analysis. The planned workflow is: import data, profile and quality-control it, confirm an analysis plan, run deterministic statistics, create charts, optionally obtain constrained AI-assisted interpretation, and export Word/Excel/JSON artifacts.

## Current status

Phase 0 is committed as the local baseline, Phase 1 is committed as `4bb5e06`, Phase 2A is
committed as `1b5cd90`, and the Phase 2B baseline is committed as `fe549c9`. Phase 1 provides
read-only CSV/XLSX ingestion, explicit mappings, type parsing, structural QC, and traceable JSON
outputs. Phase 2A adds confirmed measurement-row descriptive statistics for `generic_grouped`.
Phase 2B adds a confirmed, two-group, experimental-unit-level Welch comparison. Phase 3A is
baselined locally as `9280e0a` and adds a confirmed, standard-only ELISA 4PL fit. Phase 3B is
the current uncommitted work and adds research-only per-measurement inverse estimates.

Phase 2A and 2B intentionally contain no ELISA processing or fitting. Phase 3A intentionally
contains no unknown-sample back-calculation. Automatic outlier handling, imputation,
transformation, unit conversion, chart, AI integration, report renderer, database, network
function, or formal UI remain out of scope. Phase 2B does not prove independence and does not
infer biological sample size. Phase 3B preserves `curve_validated=false` and
`validated_quantification_enabled=false`, requires explicit research-use acknowledgement, does
not aggregate unknown repeats, and refuses extrapolation outside the positive standard span.

## Windows quick start

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,templates]"
python -m pytest -q
ruff check .
mypy src
```

## Phase 1 CLI

Run from the project root. The package can be used directly from the source tree with `PYTHONPATH=src` or after editable installation.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m biolab_copilot.cli list-sheets templates\biolab_copilot_templates.xlsx
python -m biolab_copilot.cli suggest-mapping examples\generic_grouped_normal.csv --experiment-type generic_grouped
python -m biolab_copilot.cli import examples\generic_grouped_normal.csv `
  --experiment-type generic_grouped `
  --mapping '{"sample_id":"sample_id","group":"group","measurement":"measurement","replicate":"replicate_id"}' `
  --output-dir outputs\phase1
```

The mapping direction is `source_column -> canonical_field`. Each run creates a new directory with `dataset_profile.json`, `validation_issues.json`, `imported_data.json`, and `run_manifest.json`. Exit code `0` means no error/blocking QC issue; `2` means an input or QC error/blocking issue; `3` means an unexpected CLI failure. Warnings are retained and do not delete records.

## Phase 2A CLI

Generate a plan from an unchanged Phase 1 `imported_data.json` artifact. Plan generation never
confirms the plan:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m biolab_copilot.cli generate-plan runs\<phase1-run>\imported_data.json `
  --output-dir outputs\phase2a-plans
```

Review the generated `analysis_plan.json`, set `confirmed` to `true`, set each listed
`warning_confirmations` entry to `true` only after review, and calculate the resulting file
SHA-256. Execute only with that exact explicit hash:

```powershell
python -m biolab_copilot.cli execute-plan outputs\phase2a-plans\<plan-run>\analysis_plan.json `
  --confirm-plan-sha256 <sha256-of-confirmed-plan> `
  --output-dir outputs\phase2a
```

Phase 2A emits `analysis_plan.json`, `analysis_result.json`, `analysis_issues.json`, and
`run_manifest.json` in a new run directory. `analysis_level=measurement_rows` and
`independent_biological_n=null` are intentional; a computed result does not establish biological
independence or inferential validity.

## Phase 2B CLI

Phase 2B requires a project-local Phase 1 `generic_grouped` import artifact and a separate JSON
design declaration. The declaration must explicitly identify the experimental-unit field, two
groups, the `none` or `mean` technical-repeat policy, and the user assumptions:

```powershell
python -m biolab_copilot.cli generate-welch-plan runs\<phase1-run>\imported_data.json `
  --design-file examples\phase2b_design.json `
  --output-dir outputs\phase2b-plans
```

Review both `experimental_units.json` and `analysis_plan.json`. Set `confirmed=true` and each
listed `warning_confirmations` entry to `true` only after review. Confirm the resulting plan
SHA-256 explicitly:

```powershell
python -m biolab_copilot.cli execute-welch outputs\phase2b-plans\<plan-run>\analysis_plan.json `
  --confirm-plan-sha256 <sha256-of-confirmed-plan> `
  --output-dir outputs\phase2b
```

Successful Phase 2B runs emit the plan, experimental-unit preview, result, issue list, and
manifest in a new run directory. `analysis_level=experimental_units`,
`independent_biological_n=null`, and `independence_status=user_declared_not_verified` are
intentional. The minimum of two experimental units per group is a computation precondition, not
evidence that a study has adequate sample size or valid assumptions.

## Phase 3A CLI

Phase 3A accepts only an `elisa_standard_curve` import artifact and a separate explicit design
declaration. The declaration fixes the curve direction, concentration/response units, replicate
policy, optimizer settings, numerical bounds, and diagnostic thresholds. It never guesses a
direction or model:

```powershell
python -m biolab_copilot.cli generate-4pl-plan runs\<phase1-run>\imported_data.json `
  --design-file examples\phase3a_design_increasing.json `
  --output-dir outputs\phase3a-plans
```

Review `standards_preview.json` and `analysis_plan.json`, then set `confirmed=true`, explicitly
confirm each listed warning, and calculate the resulting plan SHA-256:

```powershell
python -m biolab_copilot.cli execute-4pl outputs\phase3a-plans\<plan-run>\analysis_plan.json `
  --confirm-plan-sha256 <sha256-of-confirmed-plan> `
  --output-dir outputs\phase3a
```

The run emits `analysis_plan.json`, `standards_preview.json`, `curve_fit_result.json`,
`analysis_issues.json`, and `run_manifest.json`. The fit uses the declared 4PL direction and
standard concentration levels only. Sample, blank, and control rows remain in the preview but
are excluded; `curve_validated=false` and `quantification_enabled=false`, so no unknown-sample
concentration is calculated. See [docs/ELISA_4PL_DEFINITIONS.md](docs/ELISA_4PL_DEFINITIONS.md).

See [PLAN.md](PLAN.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) for the controlled roadmap. This project is not production-ready and has not completed scientific validation.

## Phase 3B CLI

Phase 3B consumes an unchanged, successfully converged Phase 3A `curve_fit_result.json` and an
explicit research-use inverse design. The design must declare context compatibility and either a
mapped `dilution_factor` field or an explicit uniform factor, including an explicit `1` for
undiluted samples:

```powershell
python -m biolab_copilot.cli generate-elisa-inverse-plan `
  outputs\phase3a\<curve-run>\curve_fit_result.json `
  --design-file examples\phase3b_inverse_design.json `
  --output-dir outputs\phase3b-plans
```

Review `sample_preview.json` and `analysis_plan.json`, set `confirmed=true`, explicitly confirm
each listed warning, and calculate the resulting plan SHA-256. Then execute with that exact hash:

```powershell
python -m biolab_copilot.cli execute-elisa-inverse `
  outputs\phase3b-plans\<plan-run>\analysis_plan.json `
  --confirm-plan-sha256 <sha256-of-confirmed-plan> `
  --output-dir outputs\phase3b
```

The output is per measurement row and uses
`concentration_in_assayed_sample`, `dilution_factor`, and
`concentration_in_original_sample`. Out-of-span rows remain null and diagnostic rather than
being extrapolated. See [docs/ELISA_4PL_INVERSE_DEFINITIONS.md](docs/ELISA_4PL_INVERSE_DEFINITIONS.md).
