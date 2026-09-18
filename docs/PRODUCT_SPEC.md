# Product Specification

## Product intent

BioLab Copilot will be a local-first, result-traceable system for small-to-medium biological experiment datasets. It will preserve source evidence, make quality concerns visible, require analysis-plan confirmation, and separate deterministic computation from optional language-model interpretation.

## Target users

- Bench scientists who need a repeatable first-pass analysis without building a statistical pipeline.
- Research associates and core-facility staff who need batchable, reviewable outputs.
- Scientific software engineers who need stable contracts and audit-friendly boundaries.
- Reviewers who need to inspect source hashes, configuration, warnings, and generated artifacts.

## Core problems

- CSV/XLSX experiment data often has inconsistent headers, missing values, repeated measurements, and undocumented assumptions.
- Ad hoc spreadsheets make it difficult to reproduce a number or determine which source file produced it.
- Outlier deletion and silent cleaning can change scientific conclusions.
- Natural-language interpretation is useful only when it is constrained by structured, deterministic results.

## v1.0 scope

- Local CSV/XLSX intake with immutable source preservation and file hashes.
- Dataset profiling and visible validation/QC issues; anomalies are marked, not silently removed.
- User confirmation of an explicit analysis plan.
- Two assay plugins: `generic_grouped` and `elisa_standard_curve`.
- Deterministic descriptive and inferential statistics appropriate to the confirmed plan.
- Reproducible charts and Word/Excel/JSON report artifacts.
- Run manifests containing input identity, configuration, software versions, warnings, and status.
- Optional AI-assisted narrative that consumes structured results only and works without network access when omitted.

## Non-goals

- Replacing a LIMS, ELN, statistical package, or regulated validation system.
- Automatic scientific judgment, automatic outlier removal, or silent imputation.
- Arbitrary code execution from prompts or direct LLM control of data and statistics.
- Real-time cloud collaboration, a GPU workflow, or a mandatory internet connection.
- Antibody sequence analysis or a required dependency on Antibody AI Research Assistant.
- Support for every assay type in v1.0.

## Complete user flow

1. User selects one or more local CSV/XLSX files.
2. The system records source bytes, path metadata, and SHA-256 hashes without changing the source.
3. The system profiles columns, row counts, missingness, duplicates, and basic type/shape alerts.
4. The system displays validation/QC issues with severity, location, suggested action, and whether anything was auto-fixed. The default policy is no auto-fix.
5. The system proposes an assay type and analysis plan. The user confirms or edits the plan.
6. The deterministic engine executes the confirmed plan and emits structured results plus warnings.
7. Visualization consumes structured results and emits chart metadata and files.
8. Optional AI consumes only structured results, warnings, and declared context, producing clearly labeled interpretation that cannot alter numeric results.
9. Reporting renders JSON, Excel, and Word artifacts from the manifest, structured results, charts, and warnings.
10. The user reviews the run manifest, artifacts, and unresolved issues; the source and derived artifacts remain traceable.

## Success criteria

- A user can identify the exact source hash, configuration, package version, warnings, and run status for every result.
- Re-running the same input and confirmed configuration produces the same deterministic numeric results.
- Missing values, high CV, out-of-range samples, and fitting problems are visible and are not silently discarded.
- The core import/profile/statistics path remains usable without an LLM, network, GPU, or external database.
- A reviewer can distinguish deterministic numbers from optional generated narrative.
- Phase-gated tests prevent unsupported assay behavior from entering the release.

## Scientific and privacy risks

- Poor plate layout, unit mistakes, edge effects, and inappropriate controls can make a mathematically correct result scientifically misleading.
- Small sample sizes and non-independent replicates can invalidate common tests; the plan must expose assumptions.
- Curve extrapolation and saturation can create false precision; out-of-range values must remain warnings or blocking issues according to a documented rule.
- User data may contain sensitive research information. Local-first storage, explicit hashes, redaction guidance, and no default network calls reduce exposure but do not replace institutional controls.
- AI narratives can sound more certain than the evidence. They must be optional, provenance-labeled, grounded in structured results, and reviewed by a scientist.
- This product requires assay-specific scientific review and validation before use for consequential decisions.

