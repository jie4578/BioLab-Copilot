# Phased implementation plan

Every phase ends with a written status review. A failed test, lint check, type check, or unresolved scientific rule blocks entry to the next phase.

Current delivery: Phase 1 is committed as `4bb5e06`; Phase 2A is committed as `1b5cd90`; Phase
2B is committed as `fe549c9`; Phase 3A is baselined as `9280e0a`; Phase 3B is committed as
`99a42974384258337b795435d605232a576f175e`; Phase 4A is committed as
`8f232b340e354ff211cbfc7f953aaedf0c3aa280`; and Phase 4B is committed as
`a9273a431488e1776eec00cb73653854ab0c9adf`. Phase 4C release hardening is the current
uncommitted work.

## Phase 0 — Foundation and contracts

- **Goal:** Establish governance, stable data contracts, synthetic fixtures, and local development checks.
- **Allowed modification:** `AGENTS.md`, project docs, `pyproject.toml`, package metadata, `contracts`, placeholders, tests for contracts, synthetic examples, and template tooling.
- **Forbidden modification:** Runtime ingestion, profiling, QC execution, statistical calculations, curve fitting, chart generation, AI calls, report rendering, databases, LangChain, LLM SDKs, Gradio, and formal UI.
- **Deliverables:** Versioned Pydantic models, enums, JSON Schema support, examples, XLSX template generator, MIT license, README, and quality configuration.
- **Test method:** Contract round trips, schema checks, invalid-field checks, extra-field checks, and `pytest`, `ruff`, `mypy`.
- **PASS standard:** All required checks pass; no business logic exists outside contracts.
- **Entry to next phase:** Phase 0 status is `READY_FOR_PHASE_1_INGESTION` and the owner authorizes Phase 1.

## Phase 1 — Read-only ingestion and profiling

- **Goal:** Import CSV/XLSX bytes without mutation and produce basic dataset profiles.
- **Allowed modification:** `ingestion`, `profiling`, related contracts, fixtures, and tests.
- **Forbidden modification:** Scientific conclusions, automatic deletion/imputation, statistics, fitting, AI, reports, and UI.
- **Deliverables:** Format/encoding handling, source hash preservation, profile output, and reviewable import errors.
- **Test method:** Synthetic CSV/XLSX round trips, hash checks, malformed-file tests, and Windows path tests.
- **PASS standard:** Source bytes are unchanged; errors are explicit; all tests and quality checks pass.
- **Entry to next phase:** Owner confirms the ingestion/profile evidence and unresolved format rules.
- **Current delivery note:** The implementation is present as uncommitted changes after the Phase 0 baseline. Phase 2 statistics, CV rules, outlier handling, and curve fitting remain forbidden until acceptance.

## Phase 2 — QC and analysis-plan confirmation

- **Goal:** Add visible validation/QC and an explicit user-confirmed plan.
- **Allowed modification:** assay validation boundaries, QC issue generation, plan proposal/confirmation, and tests.
- **Forbidden modification:** Silent cleaning, automatic outlier removal, statistical inference, AI, reports, and unconfirmed execution.
- **Deliverables:** Assay-independent issue model usage, two assay plan proposals, severity rules, and confirmation state transitions.
- **Test method:** Missingness, high CV, header, range, and blocking-issue fixtures.
- **PASS standard:** Every flag has location and suggested action; source data remains unchanged; unconfirmed plans cannot run.
- **Entry to next phase:** Scientific rules for the two assays are reviewed and the owner authorizes the relevant deterministic calculation subphase.

### Phase 2A — Generic grouped descriptive statistics and explicit plan confirmation

- **Goal:** Execute a user-confirmed, traceable descriptive plan for `generic_grouped` measurement rows only.
- **Allowed modification:** `contracts`, `statistics`, offline CLI plan generation/execution, descriptive-statistics tests, and Phase 2A documentation.
- **Forbidden modification:** ELISA processing or fitting; t tests, ANOVA, non-parametric tests, normality or variance tests, p-values, effect sizes, SEM, confidence intervals, CV, technical-repeat aggregation, pairing, biological-sample inference, outlier deletion, imputation, transformation, unit conversion, charts, reports, AI, network, database, or UI.
- **Deliverables:** Explicit `AnalysisPlan`; plan-file and SHA-256 confirmation; deterministic grouped `AnalysisResult`; warning confirmation; independent run artifacts; failure diagnostics; no `NaN` or `Infinity` JSON.
- **Test method:** Independent hand-calculated expectations for `[1,2,3]`, `[4,4,4]`, `[1,3]`, singleton groups, negative/zero values, multiple groups, repeat preservation, plan/input binding, QC blocking, ELISA rejection, overflow, and CLI exit codes.
- **PASS standard:** Only confirmed, hash-bound, analysis-ready `generic_grouped` inputs execute; all six fixed descriptive fields are reproducible; `sample_sd` uses `ddof=1`; `independent_biological_n=null`; source and Phase 1 artifacts remain unchanged.
- **Entry to next phase:** Owner accepts the Phase 2A evidence and explicitly authorizes Phase 2B inferential design. This implementation must remain uncommitted until acceptance.

### Phase 2B — Experimental design contract and two-group Welch comparison

- **Goal:** Execute one explicitly confirmed two-sided Welch comparison for one `generic_grouped` endpoint, two user-named independent groups, and explicit experimental units.
- **Allowed modification:** `contracts`, `statistics`, the offline Phase 2B CLI, experimental-unit preview/aggregation, SciPy Welch calculation, tests, and Phase 2B documentation.
- **Forbidden modification:** Pairing, repeated measures, clustering, multi-group or multi-factor tests, batch testing, ELISA processing/fitting, automatic biological-sample inference, automatic repeat classification, outlier deletion, imputation, transformation, unit conversion, charts, reports, AI, network, database, or UI.
- **Deliverables:** Explicit design declaration; plan/input/design/preview hash binding; unit-level preview; `none` and explicitly declared technical-repeat `mean` policies; deterministic Welch result and confidence interval; failure diagnostics; strict JSON and run-manifest provenance.
- **Test method:** Independent fixed-value expectations for A=`[1,2,3]` and B=`[4,5,6]`; hand-checked SD, t, df, p, and CI; repeat aggregation, identity conflicts, missing declarations, duplicate records, zero variance, changed bindings, Phase 2A/ELISA rejection, CLI exit codes, and regression tests.
- **PASS standard:** Only a confirmed, hash-bound, structurally ready two-group plan executes; every participating record has an explicit unit; source records remain preserved; warnings remain visible; results contain no `NaN` or `Infinity`; SciPy and implementation versions are recorded.
- **Entry to next phase:** Owner and scientific reviewer accept this restricted implementation. No ELISA, chart, AI, UI, or broader inferential method begins automatically.

### Phase 3A — ELISA standard-only 4PL fitting and diagnostics

- **Goal:** Execute one explicitly confirmed, deterministic 4PL fit for one `elisa_standard_curve` standard context, with a user-declared increasing or decreasing direction.
- **Allowed modification:** ELISA standard preview and aggregation, 4PL contracts, deterministic SciPy least-squares fitting, numerical diagnostics, offline CLI, synthetic fixtures, and Phase 3A documentation.
- **Forbidden modification:** Unknown-sample concentration back-calculation, 5PL, automatic direction/model selection, blank correction, normalization, weighting, robust loss, standard-point deletion, unit conversion, LOD/LLOQ/ULOQ/range claims, charts, reports, AI, network, database, or UI.
- **Deliverables:** Explicit 4PL design and plan; standard-record inclusion/exclusion preview; `none` and explicit `mean_by_concentration` policies; deterministic multi-start fitting; residual/SSE/RMSE/descriptive-R² and Jacobian diagnostics; strict JSON and run-manifest provenance.
- **Test method:** Independent rational-form synthetic increasing/decreasing curves; zero-concentration limits; parameter recovery; fixed-noise diagnostics; row-order determinism; repeat-level equal weighting; constant/nonfinite/negative/insufficient-level rejection; confirmation and hash binding; unknown-row exclusion; CLI and regression tests.
- **PASS standard:** Only a confirmed, hash-bound, structurally ready ELISA standard-only plan executes; at least six positive levels are present; all configured starts are recorded; no result contains `NaN` or `Infinity`; successful results state `curve_validated=false` and `quantification_enabled=false`.
- **Entry to next phase:** Owner and scientific reviewer accept the 4PL implementation and diagnostics. This phase does not authorize unknown-sample back-calculation, 5PL, charts, AI, reports, or UI.

### Phase 3B — Research-only unknown-sample 4PL inverse and dilution correction

- **Goal:** Produce a per-measurement research-use concentration estimate from an unchanged, numerically eligible Phase 3A 4PL curve without claiming validated quantification.
- **Allowed modification:** Additive inverse contracts, curve/sample/plan/preview hash validation, protected analytic 4PL inversion, explicit dilution correction, research-only CLI artifacts, synthetic tests, and Phase 3B documentation.
- **Forbidden modification:** Unknown-repeat aggregation, CV/SD, blank correction, 5PL, extrapolation, LOD/LLOQ/ULOQ, validated range claims, charting, reports, AI, network, database, or UI.
- **Deliverables:** Explicit research-use and dilution design; curve preflight; per-row statuses and null diagnostics; fitted endpoint span checks; sample/curve/plan/manifest provenance; strict JSON and offline CLI.
- **Test method:** Independent rational-form increasing/decreasing values; known concentration recovery; endpoint and asymptote guards; dilution factors 1 and 10; out-of-span nulls; missing/invalid factor rejection; unchanged source hashes; stale confirmation; standard/blank/control exclusion; regression tests and CLI exit codes.
- **PASS standard:** Only an explicitly confirmed plan bound to an unchanged, converged, non-severe Phase 3A curve runs. Every result states research-only semantics, no output contains `NaN` or `Infinity`, no row is silently aggregated or extrapolated, and numerical errors return a nonzero diagnostic status.
- **Entry to next phase:** Owner and scientific reviewer accept the Phase 3B evidence. Stop; do not enter charts, reports, AI, UI, LOD/LLOQ/ULOQ, or any validation claim.

### Phase 4A — Deterministic charts and Word/Excel/JSON reports

- **Goal:** Render reviewable report packages from completed, hash-validated Phase 2A, Phase 2B, Phase 3A, and optional Phase 3B artifacts without recalculating or mutating upstream results.
- **Allowed modification:** `visualization`, `reporting`, additive report contracts, fixed report templates, offline report CLI commands, synthetic acceptance fixtures, OOXML safety checks, and reporting documentation.
- **Forbidden modification:** Any new scientific calculation; source or upstream artifact mutation; plan changes; automatic row exclusion; formulas, macros, external links, network, AI, database, PDF workflow, UI, 5PL, blank correction, or validation claims.
- **Deliverables:** Deterministic chart functions; upstream schema/hash/semantic validation; `ReportManifest`; strict `report_data.json`; value-only XLSX; fixed DOCX; report-specific source and warning sections; isolated output directories.
- **Test method:** Contract round trips; deterministic chart-byte checks; synthetic generic, Welch, and ELISA CLI packages; report content checks; DOCX reopen and OOXML relationship scans; XLSX reopen, formula/macro/external-link scans; absolute-path and strict-JSON scans; offline execution checks.
- **PASS standard:** Every successful report package contains `report.docx`, `report.xlsx`, `report_data.json`, `report_manifest.json`, and chart PNGs. All upstream hashes and confirmed-plan bindings validate; outputs contain no `NaN`, `Infinity`, secrets, or absolute local paths; XLSX has no formulas/macros/external links; DOCX reopens without external relationships; source artifacts remain unchanged.
- **Entry to next phase:** Owner accepts the report artifacts, safety evidence, and known limitations. Stop; do not enter AI interpretation, UI, PDF, or release work automatically.

### Phase 4B — Local-first Gradio pilot UI

- **Goal:** Provide a simple, local-only presentation layer for the already implemented import, QC, confirmed analysis, and deterministic reporting workflows.
- **Allowed modification:** `ui`, optional Gradio packaging metadata, UI service tests, Windows startup guidance, and documentation. The service may call existing ingestion, profiling, statistics, and reporting functions directly.
- **Forbidden modification:** Scientific formulas or thresholds; CLI subprocess execution; implicit assay or design inference; source mutation; QC bypass; AI, LLM SDKs, databases, telemetry, cloud/network interfaces, or public sharing.
- **Deliverables:** Explicit assay/mapping/design controls; plan SHA-256 and warning-confirmation UX; per-session `outputs/ui-sessions/<session-id>/` isolation; display-safe issue/result summaries; safe report downloads; local startup module and `start_local.bat`.
- **Test method:** Offline service-layer tests for session isolation, stale-plan/input confirmation, error/blocking prevention, report download scope, path traversal, and app construction. Run local launch/smoke checks when the runtime permits.
- **PASS standard:** UI binds only to `127.0.0.1`, uses `share=False` and disabled analytics, calls no subprocess/provider/network/database, refuses changed or unconfirmed plans, preserves research-only ELISA semantics, and exposes only session-relative paths.
- **Entry to next phase:** Owner accepts the UI workflow and security evidence. Stop; do not add AI, cloud, database, or release behavior automatically.

### Phase 4C — Local Pilot Release Hardening

- **Goal:** Make the accepted local UI installable, launchable, demonstrable, and reviewable in a fresh supported Windows Python 3.11-3.13 environment; Python 3.13 is the current verified runtime.
- **Allowed modification:** Package metadata and single version source, Windows setup/start scripts, release and demo documentation, portable helper-runtime lookup, packaging tests, and release acceptance checks.
- **Forbidden modification:** New scientific methods, changed formulas or thresholds, contract meaning changes, AI, LLM SDKs, databases, cloud services, telemetry, public sharing, runtime network features, or access to external projects.
- **Deliverables:** `0.1.0` version strategy; `CHANGELOG.md`; Windows installation, demo, and pilot acceptance documents; path-independent setup/start scripts; wheel metadata; clean-environment evidence and known limitations.
- **Test method:** Full pytest, ruff, mypy, diff checks; editable-install and wheel metadata checks; synthetic UI smoke workflow where the supported interpreter and dependencies are available; secret/path/output scans.
- **PASS standard:** The installer selects a supported 3.11-3.13 interpreter and the current Python 3.13 path is reproducible; UI remains local-only; package, UI, and report-manifest versions agree; Python-only reports reopen safely; no user data, reports, outputs, temporary environments, or secrets enter Git.
- **Entry to next phase:** Owner accepts release evidence and known limitations. No Phase 4D or AI/cloud work begins automatically.

## Phase 3 — Deterministic statistics and ELISA curve fitting

- **Goal:** Execute only confirmed plans with reproducible statistics for the two supported assays.
- **Allowed modification:** `statistics`, assay implementations, scientific tests, and structured result contracts.
- **Forbidden modification:** LLM-generated numbers, silent exclusions, arbitrary prompt code execution, and report/UI work.
- **Deliverables:** Documented grouped statistics, replicate CV handling, 4PL/5PL decision and implementation if approved, and over-range warnings.
- **Test method:** Hand-calculated synthetic fixtures, regression tests, edge cases, and independent review of assumptions.
- **PASS standard:** Same inputs/configuration produce identical numbers; invalid/out-of-range cases are explicit; no unsupported extrapolation is hidden.
- **Entry to next phase:** Scientific reviewer signs off on formulas, tolerances, and test evidence.

## Phase 4 — Visualization and batch orchestration

- **Goal:** Render charts from structured results and support isolated batch runs.
- **Allowed modification:** `visualization`, `batch`, artifact metadata, and tests.
- **Forbidden modification:** Recomputing statistics in chart code, mutating input data, AI, and report narrative.
- **Deliverables:** Reproducible chart artifacts, batch isolation, and artifact hashes.
- **Test method:** Golden metadata tests, deterministic chart-data tests, and failure isolation tests.
- **PASS standard:** Charts trace to result IDs and source hashes; one failed run does not corrupt another.
- **Entry to next phase:** Artifact provenance and visual QA are accepted.

## Phase 5 — Audit and Word/Excel/JSON reporting

- **Goal:** Produce reviewable reports from manifests and derived artifacts.
- **Allowed modification:** `audit`, `reporting`, templates, and tests.
- **Forbidden modification:** Changing scientific results during rendering, hiding warnings, AI calls, and UI-specific business rules.
- **Deliverables:** Complete run manifest, JSON export, XLSX report, DOCX report, and warning/assumption sections.
- **Test method:** Schema validation, hash/provenance tests, report extraction tests, and rendered visual QA.
- **PASS standard:** Reports identify source hashes, configuration, software versions, warnings, and status.
- **Entry to next phase:** Report reviewer confirms traceability and readable failure states.

## Phase 6 — Optional constrained AI interpretation

- **Goal:** Add an optional narrative layer over structured deterministic results.
- **Allowed modification:** `ai` adapter, prompts, redaction policy, and tests using mocked providers.
- **Forbidden modification:** Direct data-frame/statistical execution by LLM, source deletion, conclusion mutation, mandatory network dependency, or secret leakage.
- **Deliverables:** Provider-neutral interface, structured input envelope, grounded narrative schema, and offline fallback.
- **Test method:** Mocked provider tests, prompt-injection tests, unavailable-provider tests, and provenance checks.
- **PASS standard:** AI can be disabled with no loss of core analysis; generated text is labeled and cannot alter numbers.
- **Entry to next phase:** Privacy, security, and scientific review approve the adapter boundary.

## Phase 7 — Formal UI, integration, and release hardening

- **Goal:** Expose the controlled workflow through a maintainable Windows-compatible UI and prepare a reviewed release.
- **Allowed modification:** `ui`, packaging, usability, accessibility, integration tests, and release documentation.
- **Forbidden modification:** Bypassing phase gates, hiding provenance/QC, weakening contracts, or introducing unreviewed assay rules.
- **Deliverables:** User workflow, localization boundary, packaging, support guidance, and release checklist.
- **Test method:** End-to-end synthetic runs, UI tests, Windows smoke tests, security checks, and reproducibility checks.
- **PASS standard:** Complete synthetic workflow is traceable, reversible where appropriate, and documented with known limitations.
- **Entry to release:** Owner and scientific reviewer approve the release scope; no claim of production readiness is made without separate validation.
