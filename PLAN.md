# Phased implementation plan

Every phase ends with a written status review. A failed test, lint check, type check, or unresolved scientific rule blocks entry to the next phase.

Current delivery: Phase 1 is committed as `4bb5e06`. Phase 2A implementation is complete in
the working tree and remains uncommitted pending owner acceptance. Phase 2B and all later phases
have not started.

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

### Phase 2B — Inferential design (future, not started)

- **Goal:** Review and specify whether any inferential analyses are scientifically appropriate for the supported experiment designs.
- **Allowed modification:** Future design documentation, reviewed assumptions, and tests for approved inferential contracts.
- **Forbidden modification:** Any implementation of inferential statistics, p-values, tests, ELISA fitting, charts, AI, reports, UI, or silent repeat aggregation before explicit authorization.
- **Deliverables:** Owner- and scientific-reviewer-approved inferential design decisions only.
- **Test method:** Future design review and synthetic contract tests after authorization.
- **PASS standard:** No unsupported inferential rule is implemented or implied; repeat and independence assumptions are explicit.
- **Entry to next phase:** Scientific reviewer and owner approve the design and authorize implementation.

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
