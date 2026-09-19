# BioLab Copilot agent and contributor rules

## Project principles

- Keep the system local-first, deterministic, inspectable, and traceable.
- Treat every source file as immutable evidence. Preserve the original bytes and record a SHA-256 hash.
- Profile and flag anomalies; never silently delete, overwrite, impute, or normalize scientific data.
- Generate all scientific numbers with deterministic Python code. Future language models may explain structured results but may not calculate, remove data, or change conclusions.
- Keep scientific computation independent from UI, AI providers, and report rendering.
- Prefer MIT- or Apache-2.0-compatible dependencies and do not copy GPL or AGPL code.
- Keep source code and user documentation in English. Future UI localization may add Chinese support.

## Forbidden behavior

- Do not access files outside the current project directory.
- Do not connect to or copy from Antibody AI Research Assistant.
- Do not use company data, real antibody sequences, personal information, or API keys.
- Do not make network requests in Phase 0.
- Do not add LangChain, a database, Gradio, an LLM SDK, or a formal UI in Phase 0.
- Do not commit or push unless the project owner explicitly authorizes it.
- Do not use an LLM to execute arbitrary statistical code.
- Do not silently modify scientific data or hide warnings.

## Development commands

From the repository root on Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,templates]"
python -m pytest -q
ruff check .
mypy src
```

Phase 0 does not require network access after dependencies are available locally. The XLSX template script is optional and requires the `templates` extra:

```powershell
python scripts\generate_xlsx_templates.py
```

## Testing requirements

- Add or update tests with every contract change.
- Test JSON round trips, JSON Schema presence, invalid fields, and forbidden extra fields.
- Scientific tests must use synthetic fixtures and verify deterministic outputs.
- Run all three quality commands before declaring a phase complete.
- If any test or quality check fails, fix the cause and rerun it. Never delete tests, weaken strictness, or add an unsupported ignore to obtain PASS.

## Phase gates and stop rules

- Work only within the phase explicitly authorized by the project owner.
- At the end of each phase, report scope, tests, warnings, and open decisions, then stop.
- Do not enter the next phase after a failed test or quality check.
- Stop and ask the project owner when a scientific rule or architectural choice would materially change the design.
- Phase 0 ends with contracts, documentation, synthetic examples, and tooling only. It must not implement ingestion, profiling, QC, statistics, fitting, charts, AI, reports, or formal UI.

## Phase 1 implementation boundary

- Phase 1 may implement read-only CSV/XLSX ingestion, explicit mappings, type parsing, structural QC, traceable JSON artifacts, and an offline CLI.
- Phase 1 must not implement statistical tests, CV calculations, outlier detection or deletion, curve fitting, charts, AI/API calls, Word reports, databases, network behavior, or formal UI.
- Keep raw source values and parsed values side by side with source locations. `analysis_ready=false` whenever an error or blocking issue exists.
- Preserve biological, technical, and unknown repeat types. Never infer pairing, independence, sample size, units, or aggregate observations.

## Phase 2B implementation boundary

- Phase 2B is restricted to `generic_grouped`, one measurement endpoint, exactly two explicitly named groups, and one confirmed two-sided Welch comparison.
- Require a separate explicit experimental-unit design declaration. `experimental_unit_id` is not inferred from `sample_id`, biological replicate metadata, repeat type, or observed values. Independence is recorded as user-declared and not software-verified.
- `none` requires one measurement row per experimental unit. `mean` requires explicit technical-repeat declarations and unique `technical_replicate_id` values within each unit. All source rows and locations remain available in the preview.
- Error/blocking QC, duplicate complete records, missing or cross-group unit IDs, unsupported designs, changed input/design/preview hashes, and unconfirmed plans block inference. Warnings remain visible and require explicit confirmation where listed by the plan.
- Phase 2B must not add paired, repeated-measures, clustered, multi-group, multi-factor, batch, ELISA, chart, AI, report, database, network, or UI behavior. Do not enter any later phase after a failed quality check.

## Phase 3A implementation boundary

- Phase 3A may implement only a confirmed `elisa_standard_curve` standard-only 4PL fit with an explicit direction and explicit replicate policy.
- Phase 3A must not back-calculate unknown samples, implement 5PL, apply blank correction, weighting, robust loss, point deletion, unit conversion, LOD/LLOQ/ULOQ rules, charts, reports, AI/API calls, databases, network behavior, or formal UI.
- Standard rows must remain traceable at both source-record and concentration-level views. Sample, blank, and control rows are retained but excluded from the fit.
- Numerical convergence is not assay validation. Every successful result must state `curve_validated=false` and `quantification_enabled=false`.

## Phase 3B implementation boundary

- Phase 3B may implement only research-use, per-measurement unknown-sample inversion from an unchanged, converged Phase 3A 4PL result.
- Require explicit `research_only_acknowledged=true`, explicit curve-context compatibility, and an explicit dilution-factor source. Never default a missing factor to 1.
- Use only the positive observed standard concentration span as an interpolation guard. Do not extrapolate, clip responses, infer dilution, aggregate unknown repeats, calculate CV/SD, or claim validated quantification.
- Preserve sample, standard, blank, and control source references. `curve_validated=false` and `validated_quantification_enabled=false` are immutable Phase 3A/3B semantics.
- Boundary-limited, rank-deficient, severely ill-conditioned, non-converged, changed, or error-containing curve artifacts block inversion. Numeric row failures remain explicit and never become zero concentrations.
- Phase 3B must not add 5PL, blank correction, LOD/LLOQ/ULOQ, charts, reports, AI/API calls, databases, network behavior, or formal UI. Do not enter a later phase after a failed quality check.

## Phase 4B implementation boundary

- Phase 4B is a local-only Gradio presentation boundary over the already implemented ingestion, QC, statistics, and reporting functions.
- The UI must use direct Python service calls; it must not invoke the CLI through subprocesses or duplicate scientific formulas.
- Experiment type, worksheet, column mapping, design declaration, plan SHA-256, warning confirmations, and report sources must be explicit user inputs.
- Session artifacts belong under `outputs/ui-sessions/<session-id>/`. Every download must resolve inside that session, reject traversal and absolute paths, and expose only session-relative names.
- Bind the server to `127.0.0.1`, use `share=False`, disable analytics, and do not add AI, LLM SDKs, databases, telemetry, cloud interfaces, or network features.
- Do not infer experimental units, independence, pairing, dilution, replicate type, or assay meaning. Preserve research-only ELISA semantics and all upstream QC warnings.
- A changed input, mapping, design, preview, or plan hash invalidates prior confirmation. Error/blocking QC always prevents execution.
- UI tests must be offline and must cover session isolation, stale confirmations, blocking behavior, path safety, and report download scope. Do not advance to a later phase after a failed test or quality check.

## Phase 4C implementation boundary

- Phase 4C may harden packaging, version metadata, Windows setup/start scripts, documentation, and portable report rendering for the accepted local pilot.
- Keep `0.1.0` consistent across the package, UI, and report manifests through one version source. Do not change contract schema versions or scientific semantics as part of release hardening.
- Setup scripts must resolve their own project directory, use a project-local `.venv`, select a supported Python 3.11-3.13 interpreter with a preference for the verified Python 3.13 environment, fail visibly, and never modify system Python, PATH, registry, security settings, or user files.
- Python 3.13 is the current verified Windows runtime; Python 3.11 and 3.12 remain unverified on the current host. Installation may require network access or a local dependency cache, while application execution and scientific analysis remain offline.
- Report generation must use declared Python dependencies (`openpyxl`, `python-docx`, and the declared plotting stack) directly. It must not depend on Codex runtimes, Node/npm, artifact-tool, hidden executables, or subprocesses.
- Release checks must not commit outputs, reports, temporary environments, caches, uploads, secrets, or `tests/phase2a-boundaries-lliqpk1e/`. Do not configure a remote, push, or create tags.
- Runtime behavior remains local-only: no AI, LLM SDK, provider, database, telemetry, cloud interface, public sharing, or network feature. Missing optional helper runtimes must fail clearly rather than being silently downloaded.
- Phase 4C is baselined in the local pilot commit; Phase 4D public-release-preparation changes remain uncommitted until explicit owner acceptance. Do not enter a later phase after a failed quality or release check.

## Phase 4D implementation boundary

- Phase 4D may add public-repository documentation, GitHub Actions configuration, package-content checks, security guidance, contribution guidance, and release checklists.
- Phase 4D must not add scientific methods, change formulas or thresholds, modify data contracts, add AI/LLM/database/cloud behavior, configure a remote, push, create tags, or rewrite Git history.
- CI may run only deterministic synthetic tests, declared dependency checks, wheel/sdist inspection, package import checks, CLI help, and UI construction smoke checks. It must not start a public server, upload artifacts, or access real experiment data.
- Python 3.11 and 3.12 are CI-planned validation targets until their matrix jobs actually pass; local verification claims must remain limited to versions actually tested on the current host.
- Public documentation must preserve research-use limitations, local-only privacy boundaries, provenance requirements, and the separation between deterministic computation and any future AI explanation layer.
- All Phase 4D changes remain uncommitted and unstaged unless the owner explicitly authorizes a separate commit. Do not modify or delete `tests/phase2a-boundaries-lliqpk1e/`.

## Phase 4A implementation boundary

- Phase 4A may render deterministic PNG charts and fixed Word/Excel/JSON report packages from completed, hash-validated Phase 2A, Phase 2B, Phase 3A, and optional Phase 3B artifacts.
- Report code must not recalculate statistics, refit curves, modify source files, alter plans, change upstream results, infer biological sample size, or silently omit records. It must preserve upstream warnings and provenance.
- Report packages must use stable templates and labels, project-relative output paths, strict JSON, no formulas/macros/external links, and no absolute local paths or secrets. Word output must be reopenable and carry no external relationships.
- Phase 4A must remain offline and must not add an LLM SDK, provider, database, network call, formal UI, PDF workflow, 5PL, or new scientific method. Chart code consumes structured results only.
- Failure to validate an upstream manifest, artifact hash, schema, plan confirmation, or report artifact is a report failure; it must not produce a successful manifest.
- This phase ends after CLI, content, OOXML, safety, and synthetic visual checks. Do not enter AI, UI, or validation-claim work automatically.
