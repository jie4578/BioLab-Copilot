# Phased implementation plan

Every phase ends with a written status review. A failed test, lint check, type check, or unresolved scientific rule blocks entry to the next phase.

Current delivery: Phases 0 through 4D are baselined in the public repository. Phase 4E.1
constrains NumPy for the unchanged Python 3.11-3.13 CI matrix and is included in baseline
`28c054396983f1b74d46fed63b7dd318b0d985c7`. Phase 5A is a documentation and public-showcase
pass on branch `docs/public-showcase`; no scientific behavior is in scope.

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
- **Delivery note:** Phase 1 read-only ingestion and structural QC are implemented and baselined. Phase 2 statistics, CV rules, outlier handling, and curve fitting were not part of Phase 1.

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
- **Entry to next phase:** Owner accepts release evidence and known limitations. Later public documentation work requires its own phase authorization.

### Phase 4D — GitHub public release preparation

- **Goal:** Prepare a reviewable public-repository package without creating a remote, pushing, tagging, or adding scientific functionality.
- **Allowed modification:** GitHub Actions CI configuration; README, changelog, architecture, security, contribution, installation, demo, acceptance, and release documentation; deterministic wheel/sdist content checks; release metadata and tests for these boundaries.
- **Forbidden modification:** Scientific formulas, thresholds, data contracts, analysis behavior, AI/LLM/database/cloud features, user data, report outputs, history rewriting, remote configuration, push, tags, or release creation.
- **Deliverables:** Python 3.11/3.12/3.13 CI matrix; pytest/ruff/mypy/build/import/help/UI-construction checks; package-content inspection; public security and contribution guidance; GitHub release instructions and checklist.
- **Test method:** Local quality checks, YAML parsing, synthetic-only package/build checks, Git history and working-tree secret scans, and wheel/sdist inspection. CI itself must not upload artifacts or start a public server.
- **PASS standard:** Public documentation is accurate and scoped; CI is parseable and contains no external scientific/provider step; wheel and sdist exclude private/generated artifacts; no sensitive current-tree or history finding remains unresolved; no remote/tag/push is created.
- **Entry to next phase:** Owner reviews the public-release package and explicitly authorizes any future remote/push/tag action.
- **Delivery note:** Phase 4D was reviewed and published before baseline `28c054396983f1b74d46fed63b7dd318b0d985c7`.

### Phase 4E.1 — Public CI dependency compatibility

- **Goal:** Keep the Python 3.11-3.13 CI matrix compatible with NumPy's supported Python range and type declarations.
- **Allowed modification:** Compatible dependency bounds, release-check assertions, and concise compatibility status notes.
- **Forbidden modification:** Removing Python versions from CI, changing the mypy target, weakening type checks, changing scientific behavior, or rewriting history.
- **Deliverables:** A bounded NumPy dependency and a regression check for the Python and mypy compatibility contract.
- **Test method:** Full pytest, ruff, mypy, build/archive inspection, and wheel metadata review.
- **PASS standard:** The declared NumPy bound is present in built metadata; Python 3.11 remains supported and targeted by CI.
- **Delivery note:** The local compatibility fix is included in baseline `28c054396983f1b74d46fed63b7dd318b0d985c7`.

### Phase 5A — Public showcase

- **Goal:** Make the public project understandable through a concise README, accurate demo, architecture overview, and genuine UI captures.
- **Allowed modification:** README and project documentation; documentation-only checks; clearly synthetic example data; genuine screenshots captured from the running local UI.
- **Forbidden modification:** Scientific formulas, data contracts, QC thresholds, report values, UI workflow logic, versions, release tags, or claims of clinical/production validation. Do not commit or push in this phase.
- **Deliverables:** A portfolio-oriented README, a 3-5 minute synthetic demo and 60-second introduction, aligned architecture/status/plan documents, and privacy-reviewed screenshots.
- **Test method:** Full pytest, ruff, mypy, diff check, relative-link and image validation, Mermaid review, and changed-file scope review.
- **PASS standard:** Public documentation matches implemented behavior; all referenced screenshot assets are genuine, readable, and privacy-reviewed; no scientific implementation changes are present.
- **Current state:** Documentation and genuine browser screenshots are complete on `docs/public-showcase` and await owner review. The screenshots were produced from real local UI interactions with synthetic inputs; no scientific implementation was changed.
